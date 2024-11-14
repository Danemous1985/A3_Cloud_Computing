import json
import boto3
from PIL import Image, ImageFile
import io
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client('s3')

# Make sure images are loaded properly
ImageFile.LOAD_TRUNCATED_IMAGES = True

def lambda_handler(event, context):
    try:
        # Get bucket and object key from event
        bucket_name = event['Records'][0]['s3']['bucket']['name']
        object_key = event['Records'][0]['s3']['object']['key']
        
        logger.info(f"Processing image: {bucket_name}/{object_key}")

        # Get image metadata first to check if it already been resized
        try:
            response = s3.head_object(Bucket=bucket_name, Key=object_key)
            if response.get('Metadata', {}).get('resized') == 'true':
                logger.info(f"Image already processed, skipping: {object_key}")
                return {
                    'statusCode': 200,
                    'body': json.dumps('Image already processed')
                }
        except Exception as e:
            logger.warning(f"Error checking metadata: {str(e)}")

        # Get image from S3 bucket
        response = s3.get_object(Bucket=bucket_name, Key=object_key)
        image_data = response['Body'].read()
        content_type = response.get('ContentType', 'image/jpeg')

        # Open image using Pillow
        image = Image.open(io.BytesIO(image_data))
        logger.info(f"Original image dimensions: {image.size}")

        # Resize if vertical height bigger 800 pixels
        max_height = 800
        if image.height > max_height:
            width_percent = max_height / float(image.height)
            new_width = int(float(image.width) * width_percent)
            image = image.resize((new_width, max_height), Image.Resampling.LANCZOS)
            logger.info(f"Resized image dimensions: {image.size}")

            # Save resized image
            buffer = io.BytesIO()
            image.save(buffer, format=image.format if image.format else 'JPEG', quality=85)
            buffer.seek(0)

            # Upload resized image back to the same location with metadata
            s3.put_object(
                Bucket=bucket_name,
                Key=object_key,
                Body=buffer,
                ContentType=content_type,
                Metadata={'resized': 'true'}  # Mark as resized
            )
            
            logger.info(f"Successfully resized and replaced image: {object_key}")
        else:
            logger.info(f"Image height ({image.height}) does not exceed max height ({max_height}), skipping resize")
            # Still mark it as processed to prevent reprocessing
            s3.copy_object(
                Bucket=bucket_name,
                CopySource={'Bucket': bucket_name, 'Key': object_key},
                Key=object_key,
                Metadata={'resized': 'true'},
                MetadataDirective='REPLACE'
            )

        return {
            'statusCode': 200,
            'body': json.dumps('Process completed successfully')
        }

    except Exception as e:
        logger.error(f"Error processing image: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error processing image: {str(e)}")
        }