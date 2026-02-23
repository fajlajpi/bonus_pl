def contact_info(request):
    """
    Context processor that adds contact information to all templates.
    """
    return {
        'support_email': 'bonus@primavera-and.cz',
        'company_name': 'PRIMAVERA ANDORRANA s.r.o.',
        'company_phone': '+420 778 799 900',
        'company_street': 'Jinonická 804/80',
        'company_city': 'Praha 5 – Košíře',
        'company_zip': '158 00',
    }