from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from .models import Building, Apartment
from .forms import BuildingForm, ApartmentUpdateForm
from decimal import Decimal

@login_required
def building_list(request):
    """List all buildings for the company"""
    if not request.user.is_company:
        messages.error(request, _("Access denied."))
        return redirect('dashboard:home')
        
    buildings = Building.objects.filter(company=request.user).order_by('-created_at')
    
    context = {
        'buildings': buildings,
        'form': BuildingForm(),
        'page_title': _('Buildings'),
    }
    return render(request, 'building/list.html', context)


def get_user_company(user):
    if user.is_company:
        return user
    if hasattr(user, 'staff_profile'):
        return user.staff_profile.company
    return user

@login_required
def building_detail(request, pk):
    """Alias building_detail to the interactive Apartment Visualizer Matrix"""
    return building_matrix_view(request, pk)


@login_required
def building_create(request):
    """Create a building and auto-generate the apartment grid"""
    if not request.user.is_company:
        return redirect('dashboard:home')
        
    if request.method == 'POST':
        form = BuildingForm(request.POST)
        if form.is_valid():
            building = form.save(commit=False)
            building.company = request.user
            building.save()
            
            # Check if JSON apartments data was provided via Excel upload
            import json
            from decimal import Decimal
            apts_json_str = request.POST.get('apartments_json')
            apts_to_create = []
            
            if apts_json_str:
                try:
                    apts_data = json.loads(apts_json_str)
                    for apt in apts_data:
                        apts_to_create.append(
                            Apartment(
                                building=building,
                                apartment_number=str(apt.get('Apartment Number', '')),
                                floor_number=int(apt.get('Floor Number', 1)),
                                entrance_number=int(apt.get('Entrance Number', 1)),
                                living_room_count=int(apt.get('Rooms Count', 1)),
                                total_area=Decimal(str(apt.get('Total Area (m2)', '50.00'))),
                                living_area=Decimal(str(apt.get('Living Area (m2)', '40.00'))),
                                balcony_area=Decimal(str(apt.get('Balcony Area (m2)', '0.00'))),
                            )
                        )
                except Exception as e:
                    messages.error(request, f"Error parsing apartments JSON: {e}")
                    # fallback to default generation
                    apts_to_create = []
            
            # Fallback auto-generation if no valid JSON
            if not apts_to_create:
                apt_counter = 1
                apts_per_floor = building.apartments_per_floor or 4
                for entrance in range(1, building.entrance_count + 1):
                    for floor in range(1, building.floor_count + 1):
                        for a in range(1, apts_per_floor + 1):
                            apts_to_create.append(
                                Apartment(
                                    building=building,
                                    apartment_number=str(apt_counter),
                                    floor_number=floor,
                                    entrance_number=entrance,
                                    total_area=Decimal('50.00'),
                                    living_area=Decimal('40.00'),
                                )
                            )
                            apt_counter += 1
                        
            Apartment.objects.bulk_create(apts_to_create)
            
            # Update apartment count on building
            building.apartment_count = len(apts_to_create)
            building.save(update_fields=['apartment_count'])
            
            messages.success(request, _("Building created successfully! Apartments grid generated."))
            return redirect('building:matrix', pk=building.pk)
    else:
        form = BuildingForm()
        
    return render(request, 'building/form.html', {'form': form, 'page_title': _('Add Building')})


@login_required
def apartment_update(request, pk):
    """Update apartment details via HTMX modal (Read-only if SOLD)"""
    company = get_user_company(request.user)
    apartment = get_object_or_404(Apartment, pk=pk, building__company=company)
    
    is_sold = (apartment.status == 'SOLD')
    active_contract = apartment.contracts.filter(status='ACTIVE').first()
    
    if is_sold and request.method == 'POST':
        messages.error(request, _("Sold apartments cannot be modified."))
        if request.headers.get('HX-Request'):
            return render(request, 'building/partials/apartment_modal.html', {
                'apt': apartment,
                'is_sold': True,
                'active_contract': active_contract,
                'error': _("Sold apartments cannot be modified.")
            })
        return redirect('building:matrix', pk=apartment.building.pk)

    if request.method == 'POST' and not is_sold:
        form = ApartmentUpdateForm(request.POST, request.FILES, instance=apartment)
        if form.is_valid():
            form.save()
            if request.headers.get('HX-Request'):
                return render(request, 'building/partials/apartment_card.html', {'apt': apartment})
            messages.success(request, _("Apartment updated!"))
            return redirect('building:matrix', pk=apartment.building.pk)
    else:
        form = ApartmentUpdateForm(instance=apartment)
        
    context = {
        'form': form, 
        'apt': apartment, 
        'is_sold': is_sold, 
        'active_contract': active_contract
    }
    if request.headers.get('HX-Request'):
        return render(request, 'building/partials/apartment_modal.html', context)
        
    return render(request, 'building/apartment_form.html', context)


@login_required
def building_matrix_view(request, pk):
    """Interactive visual floor-by-entrance matrix layout for building apartments"""
    building = get_object_or_404(Building, pk=pk)
    
    # Permission check: company owner or assigned staff
    if request.user.is_company and building.company != request.user:
        return redirect('dashboard:home')

    apartments = building.apartments.filter(is_real=True)
    
    # Stats
    available_count = apartments.filter(status='AVAILABLE').count()
    reserved_count = apartments.filter(status='RESERVED').count()
    sold_count = apartments.filter(status='SOLD').count()
    
    # Structure matrix dict: matrix[entrance][floor] = list_of_apartments
    matrix = {}
    for entrance in range(1, building.entrance_count + 1):
        matrix[entrance] = {}
        for floor in range(building.floor_count, 0, -1):  # Top floor down to floor 1
            matrix[entrance][floor] = apartments.filter(
                entrance_number=entrance, floor_number=floor
            ).order_by('apartment_number')
            
    return render(request, 'building/matrix.html', {
        'building': building,
        'matrix': matrix,
        'available_count': available_count,
        'reserved_count': reserved_count,
        'sold_count': sold_count,
        'page_title': f"{building.name} - Visualizer Matrix"
    })

