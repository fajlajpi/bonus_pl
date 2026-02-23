from django import template
import datetime
from django.utils.dateformat import format

register = template.Library()

@register.filter
def multiply(value, arg):
    """Multiplies the value by the argument."""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def dict_get(dictionary, key):
    """Gets a value from a dictionary by key."""
    if hasattr(dictionary, 'get'):
        return dictionary.get(key)
    return None

@register.filter
def divide(value, arg):
    return value / arg

@register.filter
def subtract(value, arg):
    """Subtract the arg from the value."""
    return value - arg

@register.filter
def sum_attr(items, attr_name):
    """Calculate the sum of a specific attribute across a list of dictionaries."""
    try:
        return sum(item[attr_name] for item in items)
    except (KeyError, TypeError):
        return 0

@register.filter
def range_loop(value):
    """Create a range from 1 to value."""
    try:
        return range(1, int(value) + 1)
    except (ValueError, TypeError):
        return range(1)

@register.simple_tag
def year_range(start_year, end_year):
    """Create a list of years from start_year to end_year (inclusive)."""
    try:
        start = int(start_year)
        end = int(end_year) + 1
        return range(start, end)
    except (ValueError, TypeError):
        current_year = datetime.datetime.now().year
        return range(current_year - 5, current_year + 1)
    
@register.filter
def czech_date(value, format_string=None):
    """
    Convert a date to Czech format.
    
    This filter converts a date to Czech format with Czech month names.
    If format_string is provided, it uses the Django date format syntax.
    If no format_string is provided, it defaults to "j. F Y" (e.g., "29. dubna 2025").
    
    Usage:
    {{ date_value|czech_date }}  -> "29. dubna 2025"
    {{ date_value|czech_date:"j. F Y" }}  -> "29. dubna 2025"
    {{ date_value|czech_date:"j.n.Y" }}  -> "29.4.2025"
    
    Args:
        value: A datetime.date or datetime.datetime object
        format_string: Optional format string using Django date format syntax
        
    Returns:
        str: The formatted date string in Czech
    """
    if value is None:
        return ''
    
    # Define Czech month names (in genitive case for proper Czech date formatting)
    czech_months = {
        1: 'ledna',
        2: 'února',
        3: 'března',
        4: 'dubna',
        5: 'května',
        6: 'června',
        7: 'července',
        8: 'srpna',
        9: 'září',
        10: 'října',
        11: 'listopadu',
        12: 'prosince'
    }
    
    # Convert string to date if necessary
    if isinstance(value, str):
        try:
            # Try to parse the string as a date
            value = datetime.datetime.strptime(value, "%B %d, %Y").date()
        except ValueError:
            try:
                # Try with different format
                value = datetime.datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                # Return the original value if it can't be parsed
                return value
    
    # Ensure we have a date or datetime object
    if not isinstance(value, (datetime.date, datetime.datetime)):
        return value
    
    # Default format if none provided
    if format_string is None:
        format_string = "j. F Y"
    
    # Create the basic formatted date
    formatted_date = format(value, format_string)
    
    # Replace month names with Czech versions if the format includes a textual month
    if "F" in format_string:
        for month_num, czech_month in czech_months.items():
            # Get English month name by creating a date with that month
            english_month = datetime.date(2000, month_num, 1).strftime("%B")
            # Replace the English month with the Czech month
            formatted_date = formatted_date.replace(english_month, czech_month)
    
    # Also check for abbreviated month names
    if "M" in format_string:
        for month_num, czech_month in czech_months.items():
            # Get English month abbreviation
            english_month = datetime.date(2000, month_num, 1).strftime("%b")
            # Replace with first 3 letters of Czech month name
            czech_abbr = czech_month[:3] + "." if len(czech_month) > 3 else czech_month
            formatted_date = formatted_date.replace(english_month, czech_abbr)
    
    return formatted_date