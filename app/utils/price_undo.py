"""Undo planning for price changes (pure Python, no Django needed).

``plan_undo`` looks at the history rows the user wants to roll back and at the batches as they
are *right now*, and decides, row by row, what is safe to do. Nothing here touches the database,
so every rule can be tested with `python -I tests/test_price_undo_pure.py`.

Safety rules (a rollback must never overwrite somebody else's later work):

* a row is reverted only if the batch still holds exactly the price that row set;
* if the batch already holds the old price, the row is reported as "already reverted";
* if the price was changed again afterwards, the row is skipped and reported;
* the old price must still be valid today (not below the batch's *current* cost, nor below the
  minimum margin that applies today);
* only batch selling prices can be undone here (product price / discount come in a later step).
"""
from decimal import Decimal

CENT = Decimal('0.01')

ST_REVERT = 'revert'
ST_ALREADY = 'already'
ST_CHANGED = 'changed'
ST_MISSING = 'missing'
ST_BELOW_COST = 'below_cost'
ST_UNSUPPORTED = 'unsupported'

FIELD_BATCH_SELLING = 'batch_selling_price'

LABELS = {
    ST_REVERT: 'Will be reverted',
    ST_ALREADY: 'Already at the old price',
    ST_CHANGED: 'Changed again since',
    ST_MISSING: 'Batch no longer exists',
    ST_BELOW_COST: 'Old price is below cost / minimum margin now',
    ST_UNSUPPORTED: 'Cannot be undone here',
}


def _d(value):
    if value is None:
        return None
    return Decimal(str(value)).quantize(CENT)


def plan_undo(rows, state, validate=None):
    """Decide what to do with each history row.

    rows      list of dicts: id, price_field, batch_id, old, new, product_name, batch_ref
    state     {batch_id: {'price': current selling price, 'cost': current cost price,
               'min_margin': optional minimum margin % that applies to the batch today}};
              a batch missing from this dict no longer exists
    validate  optional callable(cost, price) that raises ValueError for an invalid price
              (pass ``pricing.check_selling_price``)

    Returns a list of items (oldest row first), each a dict with log_id, batch_id, product_name,
    batch_ref, current, target, status and message. Rows are processed newest first against a
    simulated copy of ``state``, so two changes to one batch in the same run roll back in the
    right order.
    """
    sim = {bid: dict(v) for bid, v in state.items()}
    items = []
    for row in sorted(rows, key=lambda r: r['id'], reverse=True):
        batch_id = row.get('batch_id')
        old, new = _d(row.get('old')), _d(row.get('new'))
        item = {
            'log_id': row['id'], 'batch_id': batch_id,
            'product_name': row.get('product_name') or '', 'batch_ref': row.get('batch_ref') or '',
            'current': None, 'target': old, 'status': None, 'message': '',
        }
        items.append(item)

        if row.get('price_field') != FIELD_BATCH_SELLING or old is None or new is None:
            item['status'] = ST_UNSUPPORTED
            item['message'] = 'Only batch selling prices can be undone.'
            continue
        batch = sim.get(batch_id) if batch_id is not None else None
        if batch is None:
            item['status'] = ST_MISSING
            item['message'] = 'The batch was deleted.'
            continue

        current = _d(batch['price'])
        item['current'] = current
        if current == old:
            item['status'] = ST_ALREADY
            item['message'] = 'Nothing to do.'
            continue
        if current != new:
            item['status'] = ST_CHANGED
            item['message'] = f'Price was changed again (now {current:,.2f}); left untouched.'
            continue
        if validate is not None:
            try:
                pct = batch.get('min_margin')
                if pct is None:
                    validate(_d(batch['cost']), old)
                else:
                    validate(_d(batch['cost']), old, pct)
            except ValueError as exc:
                item['status'] = ST_BELOW_COST
                item['message'] = str(exc)
                continue
        item['status'] = ST_REVERT
        batch['price'] = old  # so an older row of the same batch sees the rolled-back price
    items.reverse()
    return items


def summarize(items):
    """Counts per status + whether there is anything to apply."""
    counts = {s: 0 for s in LABELS}
    for it in items:
        counts[it['status']] += 1
    return {
        'total': len(items),
        'counts': counts,
        'to_revert': counts[ST_REVERT],
        'skipped': len(items) - counts[ST_REVERT],
        'can_apply': counts[ST_REVERT] > 0,
    }


def undo_rule(run_id=None, log_id=None):
    """JSON stored on the undo rows so the history shows what was undone."""
    if run_id is not None:
        return {'undo_of_run': str(run_id)}
    return {'undo_of_log': int(log_id)}


def undo_reason(run_id=None, log_id=None, extra=''):
    base = f'Undo of run {str(run_id)[:8]}' if run_id is not None else f'Undo of change #{log_id}'
    extra = (extra or '').strip()
    return (f'{base}: {extra}' if extra else base)[:255]
