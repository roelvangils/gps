"""Location services for GPS Toolkit - geocoding, elevation, POIs"""

import logging
import math
import asyncio
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import requests

from ..config import settings
from ..core.models import Address, Coordinates

logger = logging.getLogger(__name__)


class LocationService:
    """Service for location-related operations"""
    
    def __init__(self, user_agent: str = settings.USER_AGENT, thread_pool=None):
        self.user_agent = user_agent
        self.thread_pool = thread_pool
    
    def reverse_geocode(self, lat: float, lon: float) -> Dict[str, Any]:
        """Get location data from OpenStreetMap Nominatim API"""
        url = f"{settings.NOMINATIM_URL}?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
        
        try:
            response = requests.get(
                url, 
                headers={'User-Agent': self.user_agent}, 
                timeout=settings.REQUEST_TIMEOUT_S
            )
            response.raise_for_status()
            data = response.json()
            
            address = data.get('address', {})
            
            # Extract address components
            house_number = address.get('house_number', '')
            road = address.get('road', 'Unknown road')
            postal_code = address.get('postcode', '')
            city = (address.get('city') or 
                   address.get('city_district') or 
                   address.get('town') or 
                   address.get('village') or 
                   'Unknown city')
            country = address.get('country', 'Unknown country')
            country_code = address.get('country_code', '').upper()
            state = address.get('state', '')
            
            # Fix Belgium country name
            if 'Belg' in country:
                country = 'Belgium'
            
            # Format street address
            street = f"{road} {house_number}".strip() if house_number else road
            
            return {
                'coordinates': {'lat': lat, 'lon': lon},
                'address': {
                    'street': street,
                    'postal_code': postal_code,
                    'city': city,
                    'state': state,
                    'country': country,
                    'country_code': country_code
                }
            }
            
        except requests.RequestException as e:
            logger.warning(f"Failed to get location data for lat={lat}, lon={lon}: {e}")
            return {
                'coordinates': {'lat': lat, 'lon': lon},
                'address': {
                    'street': 'Unknown',
                    'postal_code': '',
                    'city': 'Unknown',
                    'state': '',
                    'country': 'Unknown',
                    'country_code': ''
                }
            }
    
    def get_elevation(self, lat: float, lon: float) -> Optional[float]:
        """Get elevation data from Open Elevation API"""
        url = f"{settings.OPEN_ELEVATION_URL}?locations={lat},{lon}"
        
        try:
            response = requests.get(url, timeout=settings.REQUEST_TIMEOUT_S)
            response.raise_for_status()
            data = response.json()
            
            if 'results' in data and data['results']:
                return data['results'][0].get('elevation')
                
        except requests.RequestException as e:
            logger.warning(f"Failed to get elevation data for lat={lat}, lon={lon}: {e}")
            
        return None
    
    def get_nearby_pois(self, lat: float, lon: float, distance_m: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get nearby points of interest from Overpass API"""
        radius = distance_m or settings.POI_SEARCH_RADIUS_M
        query = f'''[out:json][timeout:{settings.REQUEST_TIMEOUT_S}];(
            node["tourism"](around:{radius},{lat},{lon});
            node["historic"](around:{radius},{lat},{lon});
            node["amenity"~"^(museum|theatre|library|place_of_worship|university|college)$"](around:{radius},{lat},{lon});
            way["tourism"](around:{radius},{lat},{lon});
            way["historic"](around:{radius},{lat},{lon});
            way["amenity"~"^(museum|theatre|library|place_of_worship|university|college)$"](around:{radius},{lat},{lon});
        );out body;>;out skel qt;'''
        
        url = settings.OVERPASS_API_URL
        
        try:
            response = requests.post(
                url, 
                data={'data': query}, 
                headers={'User-Agent': self.user_agent}, 
                timeout=settings.REQUEST_TIMEOUT_S
            )
            response.raise_for_status()
            data = response.json()
            
            pois = []
            for element in data.get('elements', []):
                if 'tags' in element and 'name' in element['tags']:
                    # Get coordinates based on element type
                    if element['type'] == 'node':
                        poi_lat = element.get('lat')
                        poi_lon = element.get('lon')
                    elif 'center' in element:
                        poi_lat = element['center'].get('lat')
                        poi_lon = element['center'].get('lon')
                    else:
                        continue
                    
                    if not poi_lat or not poi_lon:
                        continue
                    
                    tags = element['tags']
                    poi_type = (tags.get('tourism') or 
                               tags.get('historic') or 
                               tags.get('amenity', 'unknown'))
                    
                    poi = {
                        'name': tags['name'],
                        'type': poi_type.replace('_', ' ').title(),
                        'distance_m': int(self._calculate_distance(lat, lon, poi_lat, poi_lon))
                    }
                    
                    # Add optional details
                    if 'description' in tags:
                        poi['description'] = tags['description']
                    if 'wikipedia' in tags:
                        poi['wikipedia'] = tags['wikipedia']
                    
                    pois.append(poi)
            
            # Sort by distance and limit results
            pois.sort(key=lambda x: x['distance_m'])
            return pois[:settings.MAX_POIS]
            
        except requests.RequestException as e:
            logger.warning(f"Failed to get POI data for lat={lat}, lon={lon}: {e}")
            return []
    
    def get_enhanced_nearby_venues(self, lat: float, lon: float, distance_m: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Get enhanced nearby venues with additional details"""
        radius = distance_m or settings.VENUE_SEARCH_RADIUS_M
        # Query for nodes, ways, and relations
        query = f'''[out:json][timeout:{settings.REQUEST_TIMEOUT_S}];(
            node["amenity"~"^(restaurant|bar|pub|cafe)$"](around:{radius},{lat},{lon});
            way["amenity"~"^(restaurant|bar|pub|cafe)$"](around:{radius},{lat},{lon});
            relation["amenity"~"^(restaurant|bar|pub|cafe)$"](around:{radius},{lat},{lon});
        );out body;>;out skel qt;'''
        
        url = settings.OVERPASS_API_URL
        
        try:
            response = requests.post(
                url, 
                data={'data': query}, 
                headers={'User-Agent': self.user_agent}, 
                timeout=settings.REQUEST_TIMEOUT_S
            )
            response.raise_for_status()
            data = response.json()
            
            venues = []
            
            for element in data.get('elements', []):
                if 'tags' in element and 'name' in element['tags']:
                    # Get center coordinates for ways and relations
                    if element['type'] == 'node':
                        venue_lat = element.get('lat')
                        venue_lon = element.get('lon')
                    elif 'center' in element:
                        venue_lat = element['center'].get('lat')
                        venue_lon = element['center'].get('lon')
                    else:
                        continue
                    
                    if not venue_lat or not venue_lon:
                        continue
                    
                    tags = element['tags']
                    
                    venue = {
                        'name': tags['name'],
                        'type': tags.get('amenity', 'unknown'),
                        'distance_m': int(self._calculate_distance(lat, lon, venue_lat, venue_lon))
                    }
                    
                    # Add additional details if available
                    if 'opening_hours' in tags:
                        venue['opening_hours'] = tags['opening_hours']
                    if 'website' in tags:
                        venue['website'] = tags['website']
                    if 'phone' in tags:
                        venue['phone'] = tags['phone']
                    if 'cuisine' in tags:
                        venue['cuisine'] = tags['cuisine']
                    if 'wheelchair' in tags:
                        venue['wheelchair_accessible'] = tags['wheelchair'] == 'yes'
                    if 'internet_access' in tags:
                        venue['wifi'] = tags['internet_access'] in ['wlan', 'yes', 'wifi']
                    
                    venues.append(venue)
            
            # Group by type and sort by distance
            venues_by_type = {}
            for venue in venues:
                venue_type = venue['type']
                if venue_type not in venues_by_type:
                    venues_by_type[venue_type] = []
                venues_by_type[venue_type].append(venue)
            
            # Sort each type by distance and limit
            for venue_type in venues_by_type:
                venues_by_type[venue_type].sort(key=lambda x: x['distance_m'])
                venues_by_type[venue_type] = venues_by_type[venue_type][:settings.MAX_VENUES_PER_TYPE]
            
            return venues_by_type
            
        except requests.RequestException as e:
            logger.warning(f"Failed to get venue data for lat={lat}, lon={lon}: {e}")
            return {}
    
    def get_nearby_businesses(self, lat: float, lon: float, distance_m: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Get nearby businesses including shops, services, and offices"""
        radius = distance_m or settings.VENUE_SEARCH_RADIUS_M
        
        # Define business categories
        shop_types = "supermarket|convenience|bakery|clothes|electronics|pharmacy|hardware|bookshop|florist|gift|jewelry"
        service_types = "bank|post_office|lawyer|insurance|real_estate|travel_agency|dry_cleaning|laundry|hairdresser|beauty_salon"
        office_types = "office|accountant|company|financial|tax_advisor|notary|architect|consulting"
        
        # Query for various business types
        query = f'''[out:json][timeout:{settings.REQUEST_TIMEOUT_S}];(
            node["shop"~"^({shop_types})$"](around:{radius},{lat},{lon});
            way["shop"~"^({shop_types})$"](around:{radius},{lat},{lon});
            node["amenity"~"^({service_types})$"](around:{radius},{lat},{lon});
            way["amenity"~"^({service_types})$"](around:{radius},{lat},{lon});
            node["office"~"^({office_types})$"](around:{radius},{lat},{lon});
            way["office"~"^({office_types})$"](around:{radius},{lat},{lon});
            node["office"]["name"](around:{radius},{lat},{lon});
            way["office"]["name"](around:{radius},{lat},{lon});
        );out body;>;out skel qt;'''
        
        url = settings.OVERPASS_API_URL
        
        try:
            response = requests.post(
                url, 
                data={'data': query}, 
                headers={'User-Agent': self.user_agent}, 
                timeout=settings.REQUEST_TIMEOUT_S
            )
            response.raise_for_status()
            data = response.json()
            
            businesses = []
            
            for element in data.get('elements', []):
                if 'tags' in element and 'name' in element['tags']:
                    # Get center coordinates for ways
                    if element['type'] == 'node':
                        business_lat = element.get('lat')
                        business_lon = element.get('lon')
                    elif 'center' in element:
                        business_lat = element['center'].get('lat')
                        business_lon = element['center'].get('lon')
                    else:
                        continue
                    
                    if not business_lat or not business_lon:
                        continue
                    
                    tags = element['tags']
                    
                    # Determine business type and category
                    business_type = None
                    category = None
                    
                    if 'shop' in tags:
                        business_type = tags['shop']
                        category = 'shop'
                    elif 'amenity' in tags and tags['amenity'] in service_types:
                        business_type = tags['amenity']
                        category = 'service'
                    elif 'office' in tags:
                        business_type = tags.get('office', 'office')
                        category = 'office'
                    
                    if business_type:
                        business = {
                            'name': tags['name'],
                            'type': business_type.replace('_', ' ').title(),
                            'category': category,
                            'distance_m': int(self._calculate_distance(lat, lon, business_lat, business_lon))
                        }
                        
                        # Add optional details
                        if 'opening_hours' in tags:
                            business['opening_hours'] = tags['opening_hours']
                        if 'website' in tags:
                            business['website'] = tags['website']
                        if 'phone' in tags:
                            business['phone'] = tags['phone']
                        if 'wheelchair' in tags:
                            business['wheelchair_accessible'] = tags['wheelchair'] == 'yes'
                        if 'brand' in tags:
                            business['brand'] = tags['brand']
                        if 'payment:cash' in tags or 'payment:cards' in tags:
                            payment_methods = []
                            if tags.get('payment:cash') == 'yes':
                                payment_methods.append('cash')
                            if tags.get('payment:cards') == 'yes':
                                payment_methods.append('cards')
                            if payment_methods:
                                business['payment_methods'] = payment_methods
                        
                        businesses.append(business)
            
            # Group by category and type, then sort by distance
            businesses_by_category = {}
            for business in businesses:
                category = business['category']
                if category not in businesses_by_category:
                    businesses_by_category[category] = {}
                
                business_type = business['type']
                if business_type not in businesses_by_category[category]:
                    businesses_by_category[category][business_type] = []
                
                businesses_by_category[category][business_type].append(business)
            
            # Sort each type by distance and limit
            for category in businesses_by_category:
                for business_type in businesses_by_category[category]:
                    businesses_by_category[category][business_type].sort(key=lambda x: x['distance_m'])
                    # Limit to reasonable number per type
                    businesses_by_category[category][business_type] = businesses_by_category[category][business_type][:5]
            
            return businesses_by_category
            
        except requests.RequestException as e:
            logger.warning(f"Failed to get business data for lat={lat}, lon={lon}: {e}")
            return {}
    
    def get_holiday_info(self, lat: float, lon: float, date: str) -> List[Dict[str, str]]:
        """Get holiday information for the location and date"""
        # First, get country code from location
        location_data = self.reverse_geocode(lat, lon)
        country_code = location_data.get('address', {}).get('country_code', '')
        
        if not country_code or len(country_code) != 2:
            return []
        
        try:
            year = date.split('-')[0]
            url = f"{settings.NAGER_DATE_API_URL}/{year}/{country_code}"
            
            response = requests.get(url, timeout=settings.REQUEST_TIMEOUT_S)
            response.raise_for_status()
            holidays = response.json()
            
            # Find holidays for the specific date
            date_holidays = []
            for holiday in holidays:
                if holiday.get('date') == date:
                    date_holidays.append({
                        'name': holiday.get('name', ''),
                        'local_name': holiday.get('localName', ''),
                        'type': holiday.get('types', [''])[0] if holiday.get('types') else ''
                    })
            
            return date_holidays
            
        except requests.RequestException:
            return []
    
    def get_historical_events(self, date: str) -> List[str]:
        """Get historical events for a specific date from Wikipedia"""
        try:
            # Extract month and day from date
            _, month, day = date.split('-')
            month_name = {
                '01': 'January', '02': 'February', '03': 'March', '04': 'April',
                '05': 'May', '06': 'June', '07': 'July', '08': 'August',
                '09': 'September', '10': 'October', '11': 'November', '12': 'December'
            }.get(month, '')
            
            if not month_name:
                return []
            
            # Query Wikipedia for events on this date
            page_title = f"{month_name}_{int(day)}"
            url = settings.WIKIPEDIA_API_URL
            
            params = {
                'action': 'query',
                'format': 'json',
                'titles': page_title,
                'prop': 'extracts',
                'exintro': True,
                'explaintext': True,
                'exsectionformat': 'plain'
            }
            
            response = requests.get(url, params=params, timeout=settings.REQUEST_TIMEOUT_S)
            response.raise_for_status()
            data = response.json()
            
            # Extract events from the page
            pages = data.get('query', {}).get('pages', {})
            events = []
            
            for page in pages.values():
                # Check if page exists (not missing)
                if page.get('missing'):
                    continue
                    
                extract = page.get('extract', '')
                if extract:
                    # More robust extraction of events
                    lines = extract.split('\n')
                    for line in lines[:10]:  # Check more lines but still return limited results
                        line_clean = line.strip()
                        # Skip empty lines, headers, and lines that are just the date
                        if (line_clean and 
                            not line_clean.startswith(month_name) and
                            not line_clean.endswith(':') and
                            len(line_clean) > 20 and  # Skip very short lines
                            '–' in line_clean):  # Historical events often have year ranges
                            events.append(line_clean)
                            if len(events) >= 3:  # Stop once we have 3 good events
                                break
            
            return events[:3]  # Return up to 3 events
            
        except Exception:
            return []
    
    # Async versions of all methods
    async def reverse_geocode_async(self, lat: float, lon: float) -> Dict[str, Any]:
        """Async version of reverse_geocode"""
        loop = asyncio.get_event_loop()
        executor = self.thread_pool if self.thread_pool else None
        return await loop.run_in_executor(executor, self.reverse_geocode, lat, lon)
    
    async def get_elevation_async(self, lat: float, lon: float) -> Optional[float]:
        """Async version of get_elevation"""
        loop = asyncio.get_event_loop()
        executor = self.thread_pool if self.thread_pool else None
        return await loop.run_in_executor(executor, self.get_elevation, lat, lon)
    
    async def get_nearby_pois_async(self, lat: float, lon: float, distance_m: Optional[int] = None) -> List[Dict[str, Any]]:
        """Async version of get_nearby_pois"""
        loop = asyncio.get_event_loop()
        executor = self.thread_pool if self.thread_pool else None
        return await loop.run_in_executor(executor, self.get_nearby_pois, lat, lon, distance_m)
    
    async def get_enhanced_nearby_venues_async(self, lat: float, lon: float, distance_m: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Async version of get_enhanced_nearby_venues"""
        loop = asyncio.get_event_loop()
        executor = self.thread_pool if self.thread_pool else None
        return await loop.run_in_executor(executor, self.get_enhanced_nearby_venues, lat, lon, distance_m)
    
    async def get_nearby_businesses_async(self, lat: float, lon: float, distance_m: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Async version of get_nearby_businesses"""
        loop = asyncio.get_event_loop()
        executor = self.thread_pool if self.thread_pool else None
        return await loop.run_in_executor(executor, self.get_nearby_businesses, lat, lon, distance_m)
    
    async def get_holiday_info_async(self, lat: float, lon: float, date: str) -> List[Dict[str, str]]:
        """Async version of get_holiday_info"""
        loop = asyncio.get_event_loop()
        executor = self.thread_pool if self.thread_pool else None
        return await loop.run_in_executor(executor, self.get_holiday_info, lat, lon, date)
    
    async def get_historical_events_async(self, date: str) -> List[str]:
        """Async version of get_historical_events"""
        loop = asyncio.get_event_loop()
        executor = self.thread_pool if self.thread_pool else None
        return await loop.run_in_executor(executor, self.get_historical_events, date)
    
    @staticmethod
    def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates in meters using Haversine formula"""
        R = 6371000  # Earth radius in meters
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c