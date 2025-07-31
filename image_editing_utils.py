import io
import os
from PIL import Image as PIL_Image
from google.cloud import storage
from google.genai.types import Image


# Download GCS blob to file
def download_blob_to_file(bucket_name, source_blob_name, destination_file_name):
    """Downloads a blob from the bucket."""
    if not os.path.isfile(destination_file_name):
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(source_blob_name)
        if blob.exists():
            blob.download_to_filename(destination_file_name)
            print(f"Blob {source_blob_name} downloaded to {destination_file_name}.")
            return destination_file_name
        else:
            print("Error downloading blob. gcs_bucket should not include 'gs://'.\n"
                  "Otherwise, does the file exist at that path?")
            return None
        
        
def upload_file_to_gcs(bucket_name, source_file_name, destination_blob_name):
    """Uploads a file to the bucket."""
    if os.path.isfile(source_file_name):   
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(source_file_name)
        print(f"File {source_file_name} uploaded to {destination_blob_name}.")
    

def calculate_target_size_from_aspect_ratio(original_size, desired_aspect_ratio):
    orig_width, orig_height = original_size
    
    w, h = (int(dim) for dim in desired_aspect_ratio.split(":"))            
    ratio = w / h

    if ratio > 1:
        # If a wider aspect ratio is desired, keep the original height
        # and expand the width
        auto_target_size = (int(orig_width * ratio), orig_height)
    elif ratio < 1:
        # If a taller aspect ratio is desired, keep the original width
        # and expand the height
        auto_target_size = (orig_width, int(orig_height * (h / w)))
    else:
        # If square is desired, make both sides equal to the larger side
        max_side = max(original_image._pil_image.size)
        auto_target_size = (max_side, max_side)
        
    return auto_target_size

# Pads an image for outpainting.
def pad_to_target_size(
    source_image:Image,
    target_size=(1536, 1536),
    mode="RGB",
    vertical_offset_from_bottom=0,
    horizontal_offset_from_left=0,
    fill_val=255,
):
    
    vertical_offset_from_top = 1 - vertical_offset_from_bottom
    orig_image_size_w, orig_image_size_h = source_image._pil_image.size
    target_size_w, target_size_h = target_size

    insert_pt_x = int((target_size_w * horizontal_offset_from_left) - \
                      (orig_image_size_w * horizontal_offset_from_left))
    insert_pt_y = int((target_size_h * vertical_offset_from_top) - \
                      (orig_image_size_h * vertical_offset_from_top))

    if mode == "RGB":
        source_image_padded = PIL_Image.new(
            mode, target_size, color=(fill_val, fill_val, fill_val)
        )
    elif mode == "L":
        source_image_padded = PIL_Image.new(mode, target_size, color=(fill_val))
    else:
        raise ValueError("source image mode must be RGB or L.")

    source_image_padded.paste(source_image._pil_image, (insert_pt_x, insert_pt_y))
    
    # Convert back to genai.types.Image
    genai_image_padded = Image(image_bytes=get_bytes_from_pil(source_image_padded))
    
    return genai_image_padded


# Gets the image bytes from a PIL Image object.
def get_bytes_from_pil(image: PIL_Image) -> bytes:
    byte_io_png = io.BytesIO()
    image.save(byte_io_png, "PNG")
    return byte_io_png.getvalue()


# Pads and resizes image and mask to the same target size.
def pad_and_mask_image(
    original_image:Image,
    target_size,
    vertical_offset_from_bottom,
    horizontal_offset_from_left,
):
    orig_w, orig_h = original_image._pil_image.size
    target_w, target_h = target_size
    
    # If we are shrinking either dimension, get the smaller
    # ration and resize by that amount
    if (target_w / orig_w) < 1 or (target_h /orig_h) < 1:
        resize_ratio = min((target_w/orig_w), (target_h/orig_h))
        new_size = (int(orig_w * resize_ratio),
                    int(orig_h * resize_ratio))
        resized_pil = original_image._pil_image.resize(new_size)
        original_image = Image(image_bytes=get_bytes_from_pil(resized_pil))
        orig_w, orig_h = original_image._pil_image.size

    starting_mask_pil = PIL_Image.new("L", (orig_w, orig_h), 0)
    starting_mask = Image(image_bytes=get_bytes_from_pil(starting_mask_pil))

    reframed_image = pad_to_target_size(
        original_image,
        target_size=target_size,
        mode="RGB",
        vertical_offset_from_bottom=vertical_offset_from_bottom,
        horizontal_offset_from_left=horizontal_offset_from_left,
        fill_val=0,
    )
    reframed_mask = pad_to_target_size(
        starting_mask,
        target_size=target_size,
        mode="L",
        vertical_offset_from_bottom=vertical_offset_from_bottom,
        horizontal_offset_from_left=horizontal_offset_from_left,
        fill_val=255,
    )
    return reframed_image, reframed_mask
