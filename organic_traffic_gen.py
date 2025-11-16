#!/usr/bin/env python3
"""
Organic Traffic Generator - Simulates realistic user behavior
For Docker Swarm Load Balancing Testing
"""
import asyncio
import aiohttp
import random
import time
import argparse
from dataclasses import dataclass
from typing import List, Dict
from datetime import datetime

# ==============================
# USER BEHAVIOR PROFILES
# ==============================

@dataclass
class UserProfile:
    name: str
    session_duration: tuple  # (min, max) seconds
    pages_per_session: tuple  # (min, max)
    think_time: tuple  # (min, max) seconds between requests
    endpoints: Dict[str, float]  # endpoint -> probability

# Define realistic user behaviors
PROFILES = {
    "casual_browser": UserProfile(
        name="Casual Browser",
        session_duration=(60, 300),  # 1-5 minutes
        pages_per_session=(3, 8),
        think_time=(5, 15),
        endpoints={
            "/": 0.50,
            "/product/{}": 0.20,
            "/api/data": 0.15,
            "/search?q={}": 0.15,
        }
    ),
    "power_user": UserProfile(
        name="Power User",
        session_duration=(300, 900),  # 5-15 minutes
        pages_per_session=(15, 30),
        think_time=(2, 8),
        endpoints={
            "/dashboard": 0.30,
            "/api/data": 0.30,
            "/search?q={}": 0.20,
            "/product/{}": 0.10,
            "/": 0.10,
        }
    ),
    "shopper": UserProfile(
        name="Shopper",
        session_duration=(180, 600),  # 3-10 minutes
        pages_per_session=(8, 15),
        think_time=(3, 12),
        endpoints={
            "/product/{}": 0.40,
            "/search?q={}": 0.30,
            "/checkout": 0.20,
            "/": 0.10,
        }
    ),
    "bot": UserProfile(
        name="Bot/Crawler",
        session_duration=(600, 3600),  # 10-60 minutes
        pages_per_session=(50, 200),
        think_time=(0.5, 2),
        endpoints={
            "/": 0.20,
            "/product/{}": 0.25,
            "/api/data": 0.25,
            "/dashboard": 0.15,
            "/search?q={}": 0.15,
        }
    ),
    "mobile_user": UserProfile(
        name="Mobile User",
        session_duration=(60, 180),  # 1-3 minutes
        pages_per_session=(2, 5),
        think_time=(8, 20),
        endpoints={
            "/": 0.60,
            "/product/{}": 0.20,
            "/api/data": 0.15,
            "/search?q={}": 0.05,
        }
    ),
}

# Profile distribution (probabilities sum to 1.0)
PROFILE_DISTRIBUTION = {
    "casual_browser": 0.40,
    "power_user": 0.25,
    "shopper": 0.20,
    "bot": 0.10,
    "mobile_user": 0.05,
}

# ==============================
# USER SESSION SIMULATOR
# ==============================

class UserSession:
    def __init__(self, session_id: int, profile: UserProfile, target_url: str):
        self.session_id = session_id
        self.profile = profile
        self.target_url = target_url
        self.requests_made = 0
        self.start_time = time.time()
        self.session_duration = random.uniform(*profile.session_duration)
        self.total_pages = random.randint(*profile.pages_per_session)
        self.stats = {
            "requests": 0,
            "success": 0,
            "errors": 0,
            "total_response_time": 0,
            "servers_hit": set(),
        }
    
    def should_continue(self) -> bool:
        """Check if session should continue"""
        elapsed = time.time() - self.start_time
        return elapsed < self.session_duration and self.requests_made < self.total_pages
    
    def get_next_endpoint(self) -> str:
        """Select next endpoint based on profile probabilities"""
        endpoints = list(self.profile.endpoints.keys())
        probabilities = list(self.profile.endpoints.values())
        endpoint = random.choices(endpoints, weights=probabilities)[0]
        
        # Fill in placeholders
        if "{}" in endpoint:
            if "product" in endpoint:
                endpoint = endpoint.format(f"item{random.randint(1, 1000)}")
            elif "search" in endpoint:
                queries = ["laptop", "phone", "book", "shoes", "watch", "camera"]
                endpoint = endpoint.format(random.choice(queries))
        
        return endpoint
    
    def get_think_time(self) -> float:
        """Get random think time between requests"""
        return random.uniform(*self.profile.think_time)
    
    async def make_request(self, session: aiohttp.ClientSession, endpoint: str):
        """Make a single HTTP request"""
        url = f"{self.target_url}{endpoint}"
        start = time.time()
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                await response.read()  # Read response body
                elapsed = time.time() - start
                
                self.stats["requests"] += 1
                self.stats["success"] += 1
                self.stats["total_response_time"] += elapsed
                
                # Track which server handled request
                server_id = response.headers.get("X-Server-ID", "unknown")
                self.stats["servers_hit"].add(server_id)
                
                return {
                    "status": response.status,
                    "server_id": server_id,
                    "response_time": elapsed,
                }
        except Exception as e:
            self.stats["requests"] += 1
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e),
                "response_time": time.time() - start,
            }
    
    async def run(self):
        """Run complete user session"""
        async with aiohttp.ClientSession() as session:
            while self.should_continue():
                endpoint = self.get_next_endpoint()
                result = await self.make_request(session, endpoint)
                
                self.requests_made += 1
                
                # Think time before next request
                if self.should_continue():
                    think_time = self.get_think_time()
                    await asyncio.sleep(think_time)
        
        return self.stats

# ==============================
# TRAFFIC GENERATOR
# ==============================

class OrganicTrafficGenerator:
    def __init__(self, target_url: str, concurrent_users: int, duration: int):
        self.target_url = target_url
        self.concurrent_users = concurrent_users
        self.duration = duration
        self.active_sessions = []
        self.completed_sessions = []
        self.start_time = None
    
    def select_profile(self) -> UserProfile:
        """Select user profile based on distribution"""
        profiles = list(PROFILE_DISTRIBUTION.keys())
        probabilities = list(PROFILE_DISTRIBUTION.values())
        profile_name = random.choices(profiles, weights=probabilities)[0]
        return PROFILES[profile_name]
    
    async def spawn_user(self, session_id: int):
        """Spawn a single user session"""
        profile = self.select_profile()
        user = UserSession(session_id, profile, self.target_url)
        stats = await user.run()
        self.completed_sessions.append(stats)
    
    async def run(self):
        """Run traffic generator"""
        print(f"🚀 Starting Organic Traffic Generator")
        print(f"   Target: {self.target_url}")
        print(f"   Concurrent Users: {self.concurrent_users}")
        print(f"   Duration: {self.duration}s")
        print(f"   Profile Distribution: {PROFILE_DISTRIBUTION}")
        print()
        
        self.start_time = time.time()
        session_id = 0
        
        # Maintain concurrent user count
        while time.time() - self.start_time < self.duration:
            # Remove completed sessions
            self.active_sessions = [s for s in self.active_sessions if not s.done()]
            
            # Spawn new users to maintain target concurrency
            while len(self.active_sessions) < self.concurrent_users:
                task = asyncio.create_task(self.spawn_user(session_id))
                self.active_sessions.append(task)
                session_id += 1
            
            await asyncio.sleep(1)  # Check every second
        
        # Wait for remaining sessions to complete
        print("\n⏳ Waiting for active sessions to complete...")
        await asyncio.gather(*self.active_sessions, return_exceptions=True)
        
        self.print_summary()
    
    def print_summary(self):
        """Print traffic generation summary"""
        total_requests = sum(s["requests"] for s in self.completed_sessions)
        total_success = sum(s["success"] for s in self.completed_sessions)
        total_errors = sum(s["errors"] for s in self.completed_sessions)
        total_response_time = sum(s["total_response_time"] for s in self.completed_sessions)
        
        all_servers = set()
        for s in self.completed_sessions:
            all_servers.update(s["servers_hit"])
        
        avg_response_time = total_response_time / total_requests if total_requests > 0 else 0
        
        print("\n" + "="*60)
        print("📊 TRAFFIC GENERATION SUMMARY")
        print("="*60)
        print(f"Total Sessions:      {len(self.completed_sessions)}")
        print(f"Total Requests:      {total_requests}")
        print(f"Successful:          {total_success} ({total_success/total_requests*100:.1f}%)")
        print(f"Errors:              {total_errors} ({total_errors/total_requests*100:.1f}%)")
        print(f"Avg Response Time:   {avg_response_time:.3f}s")
        print(f"Servers Hit:         {len(all_servers)} ({', '.join(sorted(all_servers))})")
        print(f"Duration:            {time.time() - self.start_time:.1f}s")
        print("="*60)

# ==============================
# SCENARIO PRESETS
# ==============================

async def scenario_normal_day(target_url: str):
    """Normal day traffic pattern"""
    print("📅 Scenario: Normal Day Traffic")
    generator = OrganicTrafficGenerator(target_url, concurrent_users=50, duration=600)
    await generator.run()

async def scenario_flash_sale(target_url: str):
    """Flash sale burst pattern"""
    print("🔥 Scenario: Flash Sale Burst")
    generator = OrganicTrafficGenerator(target_url, concurrent_users=150, duration=300)
    await generator.run()

async def scenario_gradual_ramp(target_url: str):
    """Gradual traffic increase"""
    print("📈 Scenario: Gradual Ramp Up")
    
    stages = [
        (30, 20),   # 30s at 20 users
        (30, 40),   # 30s at 40 users
        (30, 60),   # 30s at 60 users
        (30, 80),   # 30s at 80 users
        (30, 100),  # 30s at 100 users
    ]
    
    for duration, users in stages:
        print(f"   Stage: {users} concurrent users for {duration}s")
        generator = OrganicTrafficGenerator(target_url, users, duration)
        await generator.run()

async def scenario_stress_test(target_url: str):
    """High load stress test"""
    print("⚡ Scenario: Stress Test (High Load)")
    generator = OrganicTrafficGenerator(target_url, concurrent_users=200, duration=180)
    await generator.run()

# ==============================
# CLI
# ==============================

async def main():
    parser = argparse.ArgumentParser(description="Organic Traffic Generator")
    parser.add_argument("target", help="Target URL (e.g., http://192.168.2.50:7777)")
    parser.add_argument("--users", type=int, default=50, help="Concurrent users (default: 50)")
    parser.add_argument("--duration", type=int, default=300, help="Duration in seconds (default: 300)")
    parser.add_argument("--scenario", choices=["normal", "flash-sale", "gradual-ramp", "stress"], 
                       help="Pre-defined scenario")
    
    args = parser.parse_args()
    
    if args.scenario:
        scenarios = {
            "normal": scenario_normal_day,
            "flash-sale": scenario_flash_sale,
            "gradual-ramp": scenario_gradual_ramp,
            "stress": scenario_stress_test,
        }
        await scenarios[args.scenario](args.target)
    else:
        generator = OrganicTrafficGenerator(args.target, args.users, args.duration)
        await generator.run()

if __name__ == "__main__":
    asyncio.run(main())