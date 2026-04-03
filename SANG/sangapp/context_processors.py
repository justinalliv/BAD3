def role_display_ids(request):
    session = request.session

    if session.get('om_id') and not session.get('om_display_id'):
        session['om_display_id'] = f"{session['om_id']:03d}"
        session.modified = True

    if session.get('sales_representative_id') and not session.get('sales_representative_display_id'):
        session['sales_representative_display_id'] = f"{session['sales_representative_id']:03d}"
        session.modified = True

    if session.get('technician_id') and not session.get('technician_display_id'):
        from .models import Technician

        technician = Technician.objects.filter(id=session['technician_id']).only('technician_id').first()
        if technician:
            session['technician_display_id'] = technician.technician_id or str(session['technician_id'])
            session.modified = True

    return {}