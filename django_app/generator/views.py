from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .forms import ProductSubmissionForm, get_horizontal_files_for_category
from .models import ProductSubmission, BatchSubmission
import os
import sys
import json
from PIL import Image
import requests
from io import BytesIO
from datetime import datetime
import uuid
import shutil
from urllib.parse import quote


# Position 1 is the bottom. The column starts there and steps up by the same gap.
# 104px labels with a 41px gap = 145px between top edges.
PICTO_Y_POSITIONS = (620, 475, 330)


class ProductIconGenerator:
    def __init__(self):
        self.background_width = 800
        self.background_height = 800
        # Base directory for data files
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.data_dir = os.path.join(self.base_dir, 'Data')
        self.pictos_dir = os.path.join(self.data_dir, 'pictos')
    
    def create_background(self):
        """Load the background image file from multiple possible locations"""
        base_dir = os.path.dirname(os.path.dirname(__file__))  # django_app/
        root_dir = os.path.dirname(base_dir)  # micro/
        possible_paths = [
            os.path.join(base_dir, 'backgrounds', 'background.jpg'),
            os.path.join(base_dir, 'backgrounds', 'background.png'),
            os.path.join(root_dir, 'background.jpg'),
            os.path.join(root_dir, 'background.png'),
            os.path.join(root_dir, 'backgrounds', 'background.jpg'),
            os.path.join(root_dir, 'backgrounds', 'background.png'),
            os.path.join(root_dir, 'img', 'background.jpg'),
            os.path.join(root_dir, 'img', 'background.png')
        ]
        
        for path in possible_paths:
            try:
                background = Image.open(path)
                print(f"✅ Loaded background from: {path}")
                if background.size != (self.background_width, self.background_height):
                    background = background.resize((self.background_width, self.background_height), Image.Resampling.LANCZOS)
                return background
            except FileNotFoundError:
                continue
            except Exception as e:
                print(f"❌ Error loading {path}: {e}")
                continue
        
        print("⚠️  No background image found. Creating a simple white background.")
        background = Image.new('RGB', (self.background_width, self.background_height), (255, 255, 255))
        return background
    
    def center_product(self, product_image, background):
        """Center the product image directly on the background image without frame"""
        max_size = 500
        product_width, product_height = product_image.size
        
        if product_width > product_height:
            new_width = max_size
            new_height = int((product_height * max_size) / product_width)
        else:
            new_height = max_size
            new_width = int((product_width * max_size) / product_height)
        
        product_image = product_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Ensure product image has transparency (RGBA)
        if product_image.mode != 'RGBA':
            product_image = product_image.convert('RGBA')
        
        # Ensure background is in RGBA mode for proper alpha blending
        if background.mode != 'RGBA':
            background = background.convert('RGBA')
        
        product_x = (self.background_width - product_image.size[0]) // 2
        product_y = (self.background_height - product_image.size[1]) // 2
        
        # Paste product image with alpha channel to blend naturally (no white frame)
        background.paste(product_image, (product_x, product_y), product_image)
        
        return background
    
    def load_picto(self, picto_path, max_size=100):
        """Load a picto image, convert to RGBA, and resize preserving aspect ratio"""
        try:
            picto = Image.open(picto_path)
            if picto.mode != 'RGBA':
                picto = picto.convert('RGBA')
            
            # Resize preserving aspect ratio
            width, height = picto.size
            if width > height:
                new_width = max_size
                new_height = int((height * max_size) / width)
            else:
                new_height = max_size
                new_width = int((width * max_size) / height)
            
            picto = picto.resize((new_width, new_height), Image.Resampling.LANCZOS)
            return picto
        except Exception as e:
            print(f"❌ Error loading picto {picto_path}: {e}")
            return None

    def resolve_picto_path(self, filename):
        """Find a picto in Data/pictos, then in custom_uploads."""
        filename = os.path.basename((filename or '').strip())
        if not filename:
            return None
        main_path = os.path.join(self.pictos_dir, filename)
        if os.path.isfile(main_path):
            return main_path
        custom_path = os.path.join(self.pictos_dir, 'custom_uploads', filename)
        if os.path.isfile(custom_path):
            return custom_path
        return None
    
    def add_vertical_pictos(self, background, vertical_selections):
        """Add pictos on the left side of the image
        Position 1 = BOTTOM, Position 3 = TOP
        Only renders explicitly selected pictos - no automatic additions
        """
        picto_max_size = 104  # 20% smaller than the previous 130px labels
        x_pos = 20  # X position (left side)

        vertical_positions = PICTO_Y_POSITIONS
        
        # Filter out empty strings and None values - only keep explicitly selected pictos
        # NO automatic additions - only render what the user explicitly selected
        for i, filename in enumerate(vertical_selections):
            if filename and filename.strip() and i < len(vertical_positions):
                picto_path = self.resolve_picto_path(filename)
                picto = self.load_picto(picto_path, picto_max_size) if picto_path else None
                if picto:
                    y_pos = vertical_positions[i]
                    
                    if background.mode != 'RGBA':
                        background = background.convert('RGBA')
                    
                    background.paste(picto, (x_pos, y_pos), picto)
        
        return background
    
    def add_horizontal_pictos(self, background, horizontal_selections):
        """Add horizontal pictos vertically on the right side of the image
        Position 1 = BOTTOM, Position 3 = TOP (same Y positions as left vertical pictos)
        """
        picto_max_size = 104  # 20% smaller than the previous 130px labels
        x_pos = self.background_width - 120  # X position (right side, 120px from right edge)
        
        vertical_positions = PICTO_Y_POSITIONS
        
        for i, filename in enumerate(horizontal_selections):
            if filename and str(filename).strip() and i < len(vertical_positions):
                picto_path = self.resolve_picto_path(filename)
                picto = self.load_picto(picto_path, picto_max_size) if picto_path else None
                if picto:
                    y_pos = vertical_positions[i]
                    
                    if background.mode != 'RGBA':
                        background = background.convert('RGBA')
                    
                    background.paste(picto, (x_pos, y_pos), picto)
        
        return background
    
    def process_product(self, product_image_path, vertical_selections, horizontal_selections):
        """Process the product image with vertical and horizontal pictos"""
        try:
            # Load product image
            product_image = Image.open(product_image_path)
            
            # Convert to RGBA to preserve transparency (no white background frame)
            if product_image.mode == 'P':
                product_image = product_image.convert('RGBA')
            elif product_image.mode not in ('RGBA', 'RGB'):
                product_image = product_image.convert('RGBA')
            elif product_image.mode == 'RGB':
                # Keep RGB but we'll convert to RGBA in center_product
                pass
            
            # Create background
            background = self.create_background()
            
            # Center product on background
            background = self.center_product(product_image, background)
            
            # Add vertical pictos (left side)
            background = self.add_vertical_pictos(background, vertical_selections)
            
            # Add horizontal pictos (right side, vertical)
            background = self.add_horizontal_pictos(background, horizontal_selections)
            
            # Convert back to RGB for saving (WebP supports RGB)
            if background.mode == 'RGBA':
                rgb_background = Image.new('RGB', background.size, (255, 255, 255))
                rgb_background.paste(background, (0, 0), background)
                background = rgb_background
            
            # Save the final image as WebP
            base_name = os.path.splitext(os.path.basename(product_image_path))[0]
            output_path = f'media/results/result_{base_name}.webp'
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            background.save(output_path, 'WEBP', quality=95)
            
            return output_path
            
        except Exception as e:
            print(f"Error processing image: {e}")
            import traceback
            traceback.print_exc()
            return None


def home(request):
    """Home page with the product submission form - supports multiple images"""
    if request.method == 'POST':
        form = ProductSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            # Get uploaded files (multiple)
            files = request.FILES.getlist('product_images')
            
            if not files:
                messages.error(request, 'Please select at least one image.')
                return render(request, 'generator/home.html', {'form': form})
            
            # Create a batch submission to store the shared picto selections
            batch = BatchSubmission.objects.create(
                vertical_pos_1=form.cleaned_data.get('vertical_pos_1') or '',
                vertical_pos_2=form.cleaned_data.get('vertical_pos_2') or '',
                vertical_pos_3=form.cleaned_data.get('vertical_pos_3') or '',
                horizontal_file_1=form.cleaned_data.get('right_pos_1') or '',
                horizontal_file_2=form.cleaned_data.get('right_pos_2') or '',
                horizontal_file_3=form.cleaned_data.get('right_pos_3') or '',
            )
            
            # Gather selections from batch (3 left, 3 right), both from Data/pictos
            vertical_selections = [
                batch.vertical_pos_1, batch.vertical_pos_2, batch.vertical_pos_3,
            ]
            horizontal_selections = [
                batch.horizontal_file_1,
                batch.horizontal_file_2,
                batch.horizontal_file_3,
            ]
            
            # Process each uploaded image
            generator = ProductIconGenerator()
            success_count = 0
            
            for uploaded_file in files:
                # Reuse the product already stored under media/products/.
                # default_storage.save() would otherwise write a second file with a random suffix.
                filename = os.path.basename(uploaded_file.name)
                storage_name = f'products/{filename}'
                if default_storage.exists(storage_name):
                    file_path = storage_name
                else:
                    file_path = default_storage.save(storage_name, ContentFile(uploaded_file.read()))
                full_path = default_storage.path(file_path)
                
                # Create product submission
                submission = ProductSubmission.objects.create(
                    batch=batch,
                    product_image=file_path
                )
                
                # Process the image
                result_path = generator.process_product(
                    full_path,
                    vertical_selections,
                    horizontal_selections
                )
                
                if result_path:
                    submission.result_image = result_path.replace('media/', '')
                    submission.save()
                    success_count += 1
            
            if success_count > 0:
                messages.success(request, f'Successfully generated {success_count} product image(s)!')
                return redirect('batch_result', batch_id=batch.id)
            else:
                messages.error(request, 'Error generating product images.')
        else:
            # Form is invalid - show errors
            if form.errors:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f'{field}: {error}')
    else:
        form = ProductSubmissionForm()
    
    return render(request, 'generator/home.html', {'form': form})


def picto_public_url(filename):
    """Public URL for a file in Data/pictos or Data/pictos/custom_uploads."""
    filename = os.path.basename((filename or '').strip())
    folder = 'custom_uploads/' if filename.startswith('custom_') else ''
    return f'/data/pictos/{folder}{quote(filename)}'


def get_picto_data_from_batch(batch):
    """Extract picto data from a batch submission for preview editor
    Only includes explicitly selected pictos - no automatic additions
    Both sides load from Data/pictos
    """
    vertical_pictos = []
    vertical_positions = PICTO_Y_POSITIONS
    
    # Collect vertical pictos from batch - only include non-empty selections
    # NO automatic additions - only what the user explicitly selected
    for i in range(1, 4):
        filename = getattr(batch, f'vertical_pos_{i}', '') or ''
        if filename and filename.strip():
            vertical_pictos.append({
                'url': picto_public_url(filename),
                'x': 20,
                'y': vertical_positions[i-1]
            })
    
    horizontal_pictos = []
    x_pos = 800 - 120  # Right side, 120px from right edge
    vertical_positions = PICTO_Y_POSITIONS
    
    for i in range(1, 4):
        filename = getattr(batch, f'horizontal_file_{i}', '') or ''
        if filename and filename.strip():
            horizontal_pictos.append({
                'url': picto_public_url(filename),
                'x': x_pos,
                'y': vertical_positions[i-1]
            })
    
    return {
        'vertical': vertical_pictos,
        'horizontal': horizontal_pictos,
        'background_url': '/backgrounds/background.jpg'
    }


def result(request, submission_id):
    """Display the result page with a single generated image"""
    try:
        submission = ProductSubmission.objects.get(id=submission_id)
        
        # Get picto data for preview editor
        picto_data = {}
        if submission.batch:
            picto_data = get_picto_data_from_batch(submission.batch)
        
        return render(request, 'generator/result.html', {
            'submission': submission,
            'picto_data': json.dumps(picto_data)
        })
    except ProductSubmission.DoesNotExist:
        messages.error(request, 'Submission not found.')
        return redirect('home')


def batch_result(request, batch_id):
    """Display results for a batch of processed images"""
    try:
        batch = BatchSubmission.objects.get(id=batch_id)
        products = batch.products.all()
        
        # Get picto data for preview editor
        picto_data = get_picto_data_from_batch(batch)
        
        return render(request, 'generator/batch_result.html', {
            'batch': batch,
            'products': products,
            'picto_data': json.dumps(picto_data)
        })
    except BatchSubmission.DoesNotExist:
        messages.error(request, 'Batch not found.')
        return redirect('home')


def get_horizontal_files(request):
    """API endpoint to get files for a horizontal category"""
    category = request.GET.get('category', '')
    
    if not category:
        return JsonResponse({'files': []})
    
    files = get_horizontal_files_for_category(category)
    
    # Return list of dicts with value and display name
    file_choices = []
    for f in files:
        display_name = os.path.splitext(f)[0].replace('_', ' ').replace('-', ' ')
        file_choices.append({'value': f, 'label': display_name})
    
    return JsonResponse({'files': file_choices})


@csrf_exempt
def upload_vertical_picto(request):
    """API endpoint to upload a custom vertical picto for a specific position"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    # Get position from request
    position = request.POST.get('position')
    if not position or position not in ['1', '2', '3']:
        return JsonResponse({'error': 'Invalid position. Must be 1-3'}, status=400)
    
    # Get uploaded file
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file provided'}, status=400)
    
    uploaded_file = request.FILES['file']
    
    # Validate file extension
    filename = uploaded_file.name.lower()
    if not filename.endswith('.webp'):
        return JsonResponse({'error': 'Only .webp files are allowed'}, status=400)
    
    # Validate file size (max 5MB)
    if uploaded_file.size > 5 * 1024 * 1024:
        return JsonResponse({'error': 'File size exceeds 5MB limit'}, status=400)
    
    # Validate it's actually a valid image
    try:
        img = Image.open(uploaded_file)
        img.verify()
        uploaded_file.seek(0)  # Reset file pointer after verify
    except Exception as e:
        return JsonResponse({'error': f'Invalid image file: {str(e)}'}, status=400)
    
    # Always save temporarily to custom_uploads first
    base_dir = os.path.dirname(os.path.dirname(__file__))
    pictos_dir = os.path.join(base_dir, 'Data', 'pictos')
    custom_uploads_dir = os.path.join(pictos_dir, 'custom_uploads')
    os.makedirs(custom_uploads_dir, exist_ok=True)
    
    # Generate unique filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    safe_filename = f'custom_pos{position}_{timestamp}_{unique_id}.webp'
    file_path = os.path.join(custom_uploads_dir, safe_filename)
    
    # Save the file
    try:
        with open(file_path, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)
    except Exception as e:
        return JsonResponse({'error': f'Error saving file: {str(e)}'}, status=500)
    
    # Generate display name
    display_name = os.path.splitext(safe_filename)[0].replace('_', ' ').replace('-', ' ').title()
    
    return JsonResponse({
        'success': True,
        'filename': safe_filename,
        'display_name': display_name,
        'position': position,
        'saved_permanently': False
    })


@csrf_exempt
def save_picto_permanently(request):
    """API endpoint to save a temporarily uploaded picto permanently with a custom name"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    temp_filename = request.POST.get('temp_filename', '').strip()
    custom_name = request.POST.get('custom_name', '').strip()
    
    if not temp_filename or not custom_name:
        return JsonResponse({'error': 'Missing required parameters'}, status=400)
    
    base_dir = os.path.dirname(os.path.dirname(__file__))
    pictos_dir = os.path.join(base_dir, 'Data', 'pictos')
    custom_uploads_dir = os.path.join(pictos_dir, 'custom_uploads')
    
    # Check if temp file exists
    temp_path = os.path.join(custom_uploads_dir, temp_filename)
    if not os.path.exists(temp_path):
        return JsonResponse({'error': 'Temporary file not found'}, status=404)
    
    # Sanitize filename
    safe_name = custom_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
    # Remove any extension and add .webp
    safe_name = os.path.splitext(safe_name)[0] + '.webp'
    
    # Check if file already exists
    permanent_path = os.path.join(pictos_dir, safe_name)
    if os.path.exists(permanent_path):
        return JsonResponse({'error': f'A picto with the name "{custom_name}" already exists. Please choose a different name.'}, status=400)
    
    # Copy file from temp to permanent location
    try:
        shutil.copy2(temp_path, permanent_path)
        
        # Optionally delete temp file (or keep it for reference)
        # os.remove(temp_path)
        
        return JsonResponse({
            'success': True,
            'filename': safe_name,
            'display_name': custom_name
        })
    except Exception as e:
        return JsonResponse({'error': f'Error saving file: {str(e)}'}, status=500)
