
import requests
import asyncio
import aiohttp
import time
import random
from typing import List, Dict, Tuple
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from datetime import datetime, timedelta
import threading
import logging
from flask_sqlalchemy import SQLAlchemy

# Import db from main - this will be set when imported
db = None

# Database model for proxies
class Proxy:
    def __init__(self):
        pass
        
# This will be set when imported from main
def init_proxy_model(database):
    global db, Proxy
    db = database
    
    class ProxyModel(db.Model):
        __tablename__ = 'proxy'
        id = db.Column(db.Integer, primary_key=True)
        proxy_string = db.Column(db.String(200), nullable=False, unique=True)
        proxy_type = db.Column(db.String(10), nullable=False)  # http, socks4, socks5
        ip = db.Column(db.String(45), nullable=False)
        port = db.Column(db.Integer, nullable=False)
        is_working = db.Column(db.Boolean, default=True)
        response_time = db.Column(db.Float, nullable=True)
        last_checked = db.Column(db.DateTime, default=datetime.utcnow)
        success_rate = db.Column(db.Float, default=100.0)
        total_checks = db.Column(db.Integer, default=0)
        failed_checks = db.Column(db.Integer, default=0)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    Proxy = ProxyModel
    return ProxyModel
    id = db.Column(db.Integer, primary_key=True)
    proxy_string = db.Column(db.String(200), nullable=False, unique=True)
    proxy_type = db.Column(db.String(10), nullable=False)  # http, socks4, socks5
    ip = db.Column(db.String(45), nullable=False)
    port = db.Column(db.Integer, nullable=False)
    is_working = db.Column(db.Boolean, default=True)
    response_time = db.Column(db.Float, nullable=True)
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)
    success_rate = db.Column(db.Float, default=100.0)
    total_checks = db.Column(db.Integer, default=0)
    failed_checks = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProxyManager:
    def __init__(self):
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/91.0.864.59',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
        ]
        
    def get_random_user_agent(self):
        return random.choice(self.user_agents)
    
    def parse_proxy_string(self, proxy_string: str) -> Tuple[str, str, int]:
        """Parse proxy string and return type, ip, port"""
        proxy_string = proxy_string.strip()
        
        if proxy_string.startswith('http://'):
            proxy_type = 'http'
            proxy_string = proxy_string[7:]
        elif proxy_string.startswith('socks4://'):
            proxy_type = 'socks4'
            proxy_string = proxy_string[9:]
        elif proxy_string.startswith('socks5://'):
            proxy_type = 'socks5'
            proxy_string = proxy_string[9:]
        else:
            # Assume http if no protocol specified
            proxy_type = 'http'
        
        # Split IP and port
        if ':' in proxy_string:
            ip, port = proxy_string.split(':')
            port = int(port)
        else:
            raise ValueError("Invalid proxy format")
        
        return proxy_type, ip, port
    
    async def check_proxy(self, proxy_string: str, timeout: int = 10) -> Dict:
        """Check if a proxy is working"""
        try:
            proxy_type, ip, port = self.parse_proxy_string(proxy_string)
            
            if proxy_type == 'http':
                proxy_url = f"http://{ip}:{port}"
                proxy_dict = {'http': proxy_url, 'https': proxy_url}
            else:
                proxy_url = f"{proxy_type}://{ip}:{port}"
                proxy_dict = {'http': proxy_url, 'https': proxy_url}
            
            start_time = time.time()
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.get('http://httpbin.org/ip', proxy=proxy_url) as response:
                    if response.status == 200:
                        response_time = time.time() - start_time
                        return {
                            'working': True,
                            'response_time': response_time,
                            'error': None
                        }
                    else:
                        return {
                            'working': False,
                            'response_time': None,
                            'error': f"HTTP {response.status}"
                        }
        except Exception as e:
            return {
                'working': False,
                'response_time': None,
                'error': str(e)
            }
    
    async def bulk_check_proxies(self, proxy_list: List[str], max_concurrent: int = 100) -> List[Dict]:
        """Check multiple proxies concurrently"""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def check_with_semaphore(proxy):
            async with semaphore:
                return await self.check_proxy(proxy)
        
        tasks = [check_with_semaphore(proxy) for proxy in proxy_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return results
    
    def add_proxies_from_text(self, text_content: str) -> Dict:
        """Add proxies from text content"""
        lines = text_content.strip().split('\n')
        added_count = 0
        failed_count = 0
        duplicate_count = 0
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            try:
                proxy_type, ip, port = self.parse_proxy_string(line)
                
                # Check if proxy already exists
                existing_proxy = Proxy.query.filter_by(proxy_string=line).first()
                if existing_proxy:
                    duplicate_count += 1
                    continue
                
                new_proxy = Proxy(
                    proxy_string=line,
                    proxy_type=proxy_type,
                    ip=ip,
                    port=port
                )
                
                db.session.add(new_proxy)
                added_count += 1
                
            except Exception as e:
                failed_count += 1
                logging.error(f"Failed to parse proxy {line}: {e}")
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.error(f"Failed to save proxies: {e}")
            return {'error': str(e)}
        
        return {
            'added': added_count,
            'failed': failed_count,
            'duplicates': duplicate_count,
            'total_processed': len(lines)
        }
    
    def get_working_proxies(self, limit: int = None) -> List[Proxy]:
        """Get working proxies from database"""
        query = Proxy.query.filter_by(is_working=True).order_by(Proxy.response_time.asc())
        if limit:
            query = query.limit(limit)
        return query.all()
    
    def get_fast_proxies(self, limit: int = 100) -> List[Proxy]:
        """Get fastest working proxies optimized for view generation"""
        # First priority: Ultra-fast proxies
        query = Proxy.query.filter(
            Proxy.is_working == True,
            Proxy.response_time < 1.5,
            Proxy.success_rate > 90.0
        ).order_by(Proxy.response_time.asc())
        if limit:
            query = query.limit(limit)
        ultra_fast_proxies = query.all()
        
        # Second priority: Fast proxies
        if len(ultra_fast_proxies) < limit // 2:
            query = Proxy.query.filter(
                Proxy.is_working == True,
                Proxy.response_time < 2.5,
                Proxy.success_rate > 80.0
            ).order_by(Proxy.response_time.asc())
            if limit:
                query = query.limit(limit)
            fast_proxies = query.all()
            
            # Combine and deduplicate
            all_fast = ultra_fast_proxies + [p for p in fast_proxies if p not in ultra_fast_proxies]
            return all_fast[:limit]
        
        # Third priority: Moderately fast proxies as fallback
        if len(ultra_fast_proxies) < 10:
            query = Proxy.query.filter(
                Proxy.is_working == True,
                Proxy.response_time < 4.0,
                Proxy.success_rate > 70.0
            ).order_by(Proxy.response_time.asc())
            if limit:
                query = query.limit(limit)
            moderate_proxies = query.all()
            
            all_proxies = ultra_fast_proxies + [p for p in moderate_proxies if p not in ultra_fast_proxies]
            return all_proxies[:limit]
        
        return ultra_fast_proxies
    
    def get_proxy_for_session(self, session_id: int) -> Tuple[str, str]:
        """Get a unique fast proxy and user agent for a session"""
        # Prefer fast proxies first
        fast_proxies = self.get_fast_proxies()
        if fast_proxies:
            proxy_index = session_id % len(fast_proxies)
            selected_proxy = fast_proxies[proxy_index]
            return selected_proxy.proxy_string, self.get_random_user_agent()
        
        # Fallback to any working proxy
        working_proxies = self.get_working_proxies()
        if working_proxies:
            proxy_index = session_id % len(working_proxies)
            selected_proxy = working_proxies[proxy_index]
            return selected_proxy.proxy_string, self.get_random_user_agent()
        
        return None, self.get_random_user_agent()
    
    def get_proxies_for_frames(self, session_id: int, frame_count: int) -> List[Dict]:
        """Get optimally distributed proxies for maximum view generation effectiveness"""
        # Get the best available proxies
        fast_proxies = self.get_fast_proxies(limit=500)  # Get more proxies for better distribution
        if not fast_proxies:
            fast_proxies = self.get_working_proxies(limit=200)
        
        if not fast_proxies:
            return []
        
        frame_proxies = []
        
        # Group proxies by type for better distribution
        http_proxies = [p for p in fast_proxies if p.proxy_type.lower() == 'http']
        socks4_proxies = [p for p in fast_proxies if p.proxy_type.lower() == 'socks4']
        socks5_proxies = [p for p in fast_proxies if p.proxy_type.lower() == 'socks5']
        
        for frame_index in range(frame_count):
            # Distribute proxy types evenly
            if frame_index % 3 == 0 and http_proxies:
                proxy_pool = http_proxies
            elif frame_index % 3 == 1 and socks5_proxies:
                proxy_pool = socks5_proxies
            elif frame_index % 3 == 2 and socks4_proxies:
                proxy_pool = socks4_proxies
            else:
                proxy_pool = fast_proxies  # Fallback to all proxies
            
            # Advanced proxy selection algorithm
            # Use prime numbers to ensure good distribution
            proxy_index = (session_id * 127 + frame_index * 73 + int(time.time()) % 97) % len(proxy_pool)
            selected_proxy = proxy_pool[proxy_index]
            
            # Add randomization based on current time for each frame
            time_offset = int(time.time() * 1000) % 1000
            user_agent_seed = (session_id + frame_index + time_offset) % len(self.user_agents)
            
            frame_proxies.append({
                'proxy_string': selected_proxy.proxy_string,
                'proxy_type': selected_proxy.proxy_type,
                'user_agent': self.user_agents[user_agent_seed],
                'response_time': selected_proxy.response_time,
                'success_rate': selected_proxy.success_rate,
                'frame_id': f"f_{session_id}_{frame_index}_{time_offset}",
                'geographic_region': self.get_proxy_region(selected_proxy.ip),
                'is_premium': selected_proxy.response_time < 1.0 and selected_proxy.success_rate > 95.0
            })
        
        return frame_proxies
    
    def get_proxy_region(self, ip: str) -> str:
        """Estimate proxy geographic region from IP (simplified)"""
        try:
            first_octet = int(ip.split('.')[0])
            if first_octet in range(1, 127):
                return 'US/CA'
            elif first_octet in range(128, 191):
                return 'EU'
            elif first_octet in range(192, 223):
                return 'APAC'
            else:
                return 'OTHER'
        except:
            return 'UNKNOWN'
    
    def get_proxy_info_for_session(self, session_id: int) -> Dict:
        """Get detailed proxy information for a session"""
        fast_proxies = self.get_fast_proxies()
        if fast_proxies:
            proxy_index = session_id % len(fast_proxies)
            selected_proxy = fast_proxies[proxy_index]
            return {
                'proxy_string': selected_proxy.proxy_string,
                'proxy_type': selected_proxy.proxy_type,
                'response_time': selected_proxy.response_time,
                'success_rate': selected_proxy.success_rate,
                'last_checked': selected_proxy.last_checked,
                'is_fast': True
            }
        
        working_proxies = self.get_working_proxies()
        if working_proxies:
            proxy_index = session_id % len(working_proxies)
            selected_proxy = working_proxies[proxy_index]
            return {
                'proxy_string': selected_proxy.proxy_string,
                'proxy_type': selected_proxy.proxy_type,
                'response_time': selected_proxy.response_time,
                'success_rate': selected_proxy.success_rate,
                'last_checked': selected_proxy.last_checked,
                'is_fast': False
            }
        
        return None
    
    def abbreviate_proxy_string(self, proxy_string: str) -> str:
        """Convert full proxy to abbreviated format (last 3 digits + port + type)"""
        try:
            proxy_type, ip, port = self.parse_proxy_string(proxy_string)
            # Get last 3 digits of IP
            ip_parts = ip.split('.')
            if len(ip_parts) == 4:
                last_octet = ip_parts[-1]
                abbreviated = f"***{last_octet}:{port}"
                return f"{abbreviated} ({proxy_type.upper()})"
            return f"***:{port} ({proxy_type.upper()})"
        except:
            return "***:*** (UNK)"
    
    def get_abbreviated_proxy_info_for_session(self, session_id: int) -> Dict:
        """Get abbreviated proxy information for a session using fast proxies"""
        fast_proxies = self.get_fast_proxies()
        if fast_proxies:
            proxy_index = session_id % len(fast_proxies)
            selected_proxy = fast_proxies[proxy_index]
            return {
                'abbreviated_string': self.abbreviate_proxy_string(selected_proxy.proxy_string),
                'proxy_type': selected_proxy.proxy_type.upper(),
                'response_time': selected_proxy.response_time,
                'success_rate': selected_proxy.success_rate,
                'is_fast': True
            }
        
        working_proxies = self.get_working_proxies()
        if working_proxies:
            proxy_index = session_id % len(working_proxies)
            selected_proxy = working_proxies[proxy_index]
            return {
                'abbreviated_string': self.abbreviate_proxy_string(selected_proxy.proxy_string),
                'proxy_type': selected_proxy.proxy_type.upper(),
                'response_time': selected_proxy.response_time,
                'success_rate': selected_proxy.success_rate,
                'is_fast': False
            }
        
        return None
    
    def get_frame_proxy_details(self, session_id: int, frame_count: int) -> List[Dict]:
        """Get abbreviated proxy details for each frame"""
        fast_proxies = self.get_fast_proxies()
        if not fast_proxies:
            fast_proxies = self.get_working_proxies()
        
        if not fast_proxies:
            return []
        
        frame_details = []
        for frame_index in range(frame_count):
            proxy_index = (session_id * 100 + frame_index) % len(fast_proxies)
            selected_proxy = fast_proxies[proxy_index]
            
            frame_details.append({
                'frame_index': frame_index,
                'abbreviated_string': self.abbreviate_proxy_string(selected_proxy.proxy_string),
                'proxy_type': selected_proxy.proxy_type.upper(),
                'response_time': selected_proxy.response_time,
                'success_rate': selected_proxy.success_rate,
                'is_fast': selected_proxy.response_time < 3.0 if selected_proxy.response_time else False
            })
        
        return frame_details
    
    async def update_proxy_status(self):
        """Update proxy status by checking all proxies"""
        all_proxies = Proxy.query.all()
        proxy_strings = [p.proxy_string for p in all_proxies]
        
        if not proxy_strings:
            return
        
        results = await self.bulk_check_proxies(proxy_strings)
        
        for i, (proxy, result) in enumerate(zip(all_proxies, results)):
            if isinstance(result, Exception):
                result = {'working': False, 'response_time': None, 'error': str(result)}
            
            proxy.total_checks += 1
            proxy.last_checked = datetime.utcnow()
            
            if result['working']:
                proxy.is_working = True
                proxy.response_time = result['response_time']
            else:
                proxy.failed_checks += 1
                proxy.is_working = False
                proxy.response_time = None
            
            # Calculate success rate
            proxy.success_rate = ((proxy.total_checks - proxy.failed_checks) / proxy.total_checks) * 100
            
            # Remove proxies with very low success rate
            if proxy.total_checks >= 10 and proxy.success_rate < 10:
                db.session.delete(proxy)
        
        try:
            db.session.commit()
            logging.info(f"Updated status for {len(all_proxies)} proxies")
        except Exception as e:
            db.session.rollback()
            logging.error(f"Failed to update proxy status: {e}")

# Global proxy manager instance
proxy_manager = ProxyManager()
