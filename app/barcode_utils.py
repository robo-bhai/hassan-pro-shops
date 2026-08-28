import barcode
from barcode.writer import ImageWriter
from io import BytesIO
import base64
from PIL import Image, ImageDraw, ImageFont

def generate_barcode_image(barcode_number, product_name="", price=""):
    """
    Generate barcode image and return as base64 string
    """
    try:
        if not barcode_number:
            return ""
        
        # ✅ Agar 12-13 digits ka hai to EAN-13 use karein
        if len(barcode_number) in [12, 13]:
            if len(barcode_number) == 13:
                barcode_number = barcode_number[:12]
            ean = barcode.get('ean13', barcode_number, writer=ImageWriter())
        else:
            # ✅ Baqi sab ke liye Code-128 use karein (jo kisi bhi length ko support karta hai)
            code128 = barcode.get('code128', barcode_number, writer=ImageWriter())
            buffer = BytesIO()
            code128.write(buffer)
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return f"data:image/png;base64,{image_base64}"
        
        buffer = BytesIO()
        ean.write(buffer)
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{image_base64}"
            
    except Exception as e:
        print(f"Barcode error: {e}")
        return ""

def generate_barcode_label(barcode_number, product_name, price):
    """
    Generate a printable label with barcode, product name, and price
    """
    try:
        if not barcode_number:
            return ""
        
        # Choose barcode type based on length
        if len(barcode_number) in [12, 13]:
            if len(barcode_number) == 13:
                barcode_number = barcode_number[:12]
            barcode_obj = barcode.get('ean13', barcode_number, writer=ImageWriter())
        else:
            barcode_obj = barcode.get('code128', barcode_number, writer=ImageWriter())
        
        buffer = BytesIO()
        barcode_obj.write(buffer)
        buffer.seek(0)
        
        # Open barcode image
        barcode_img = Image.open(buffer)
        
        # Create label
        label = Image.new('RGB', (300, 150), color='white')
        draw = ImageDraw.Draw(label)
        
        # Paste barcode
        barcode_img = barcode_img.resize((250, 80))
        label.paste(barcode_img, (25, 10))
        
        # Add text
        try:
            font = ImageFont.truetype("arial.ttf", 14)
            font_small = ImageFont.truetype("arial.ttf", 12)
        except:
            font = ImageFont.load_default()
            font_small = font
        
        if len(product_name) > 25:
            product_name = product_name[:22] + "..."
        
        draw.text((10, 95), product_name, fill='black', font=font)
        draw.text((10, 115), f"Price: Rs. {price}", fill='black', font=font_small)
        draw.text((10, 130), barcode_number, fill='black', font=font_small)
        
        output_buffer = BytesIO()
        label.save(output_buffer, format='PNG')
        output_buffer.seek(0)
        
        image_base64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{image_base64}"
    except Exception as e:
        print(f"Label error: {e}")
        return ""

def generate_multiple_labels(products_data):
    """
    Generate multiple labels on one sheet
    """
    try:
        sheet = Image.new('RGB', (794, 1123), color='white')
        
        label_width = 250
        label_height = 130
        margin_x = 15
        margin_y = 10
        
        for i, product in enumerate(products_data[:24]):
            row = i // 3
            col = i % 3
            
            x = margin_x + (col * (label_width + margin_x))
            y = margin_y + (row * (label_height + margin_y))
            
            label_img_data = generate_barcode_label(
                product['barcode'],
                product['name'],
                product['price']
            )
            
            if label_img_data:
                label_base64 = label_img_data.split(',')[1]
                label_bytes = base64.b64decode(label_base64)
                label_img = Image.open(BytesIO(label_bytes))
                label_img = label_img.resize((label_width, label_height))
                sheet.paste(label_img, (x, y))
        
        buffer = BytesIO()
        sheet.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"Multiple labels error: {e}")
        return BytesIO()