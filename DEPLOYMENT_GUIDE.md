# Organic Traffic Simulator - Deployment Guide

## Overview

This system provides **realistic, organic traffic simulation** for testing Docker Swarm load balancing, plus **extreme load scenarios** for stress testing.

---

## 📦 Components

1. **organic_web_stress.py** - Web application with realistic endpoints
2. **Dockerfile** - Container image definition
3. **organic_traffic_gen.py** - Traffic generator with user behavior simulation
4. **organic_pi_controller.sh** - Controller script for your MacBook

---

## 🚀 Quick Start

### Step 1: Deploy Web Application to Docker Swarm

```bash
# 1. Build Docker image
cd /path/to/project
docker build -t docker-registry.amirmuz.com/organic-web-stress:1.0 .

# 2. Push to your registry
docker push docker-registry.amirmuz.com/organic-web-stress:1.0

# 3. Deploy to Docker Swarm (3 replicas for load balancing)
sudo docker service create \
  --name organic-web-stress \
  --replicas 3 \
  --constraint 'node.labels.zone == stress' \
  --network pymonnet-net \
  -p 7777:7777 \
  docker-registry.amirmuz.com/organic-web-stress:1.0

# 4. Verify deployment
docker service ps organic-web-stress
docker service logs organic-web-stress
```

### Step 2: Setup Raspberry Pis

```bash
# On your MacBook, make controller script executable
chmod +x organic_pi_controller.sh

# Install dependencies on all Pis
./organic_pi_controller.sh install

# Deploy traffic generator to all Pis
./organic_pi_controller.sh deploy
```

### Step 3: Test Connection

```bash
# Check if web service is accessible
curl http://192.168.2.50:7777/health

# Check service metrics
curl http://192.168.2.50:7777/metrics
```

---

## 🎯 Usage Examples

### Organic Traffic (Realistic User Behavior)

```bash
# Normal day traffic - 60 concurrent users for 5 minutes
./organic_pi_controller.sh organic-normal

# Peak hours - 120 concurrent users for 5 minutes
./organic_pi_controller.sh organic-peak

# Flash sale burst - 160 concurrent users for 3 minutes
./organic_pi_controller.sh organic-flash-sale

# Gradual ramp up - 40→80→120 users in stages
./organic_pi_controller.sh organic-gradual-ramp
```

### Extreme Load (Resource Saturation)

```bash
# Command 1: 99% ALL resources (CPU + Memory + Network)
./organic_pi_controller.sh extreme-all-99 60 30
# 60s duration, 30 users per Pi = 120 total users
# Expected: CPU ~99%, Memory ~99%, Network HIGH

# Command 2: 99% CPU + Memory ONLY (Network stays low)
./organic_pi_controller.sh extreme-cpu-mem-99 60 35
# 60s duration, 35 users per Pi = 140 total users
# Expected: CPU ~99%, Memory ~99%, Network LOW

# CPU only stress
./organic_pi_controller.sh extreme-cpu-only 45 40

# Memory only stress
./organic_pi_controller.sh extreme-memory-only 45 30
```

### Management Commands

```bash
# Check what's running
./organic_pi_controller.sh status

# View logs
./organic_pi_controller.sh logs

# Get results summary
./organic_pi_controller.sh results

# Check load distribution across backends
./organic_pi_controller.sh distribution

# Stop everything
./organic_pi_controller.sh stop
```

---

## 📊 Monitoring in Grafana

### Key Metrics to Watch

**During Organic Traffic:**

- Request distribution across 3 backend servers (should be ~33% each)
- Response time consistency (p50, p95, p99)
- Active sessions per server
- Error rates

**During Extreme Load:**

- CPU utilization (should hit ~99%)
- Memory utilization (should hit ~99%)
- Network throughput (depends on command)
- Request success rate

### Endpoints for Metrics

```bash
# Get server metrics
curl http://192.168.2.50:7777/metrics

# Get request distribution stats
curl http://192.168.2.50:7777/request-stats

# Health check
curl http://192.168.2.50:7777/health
```

---

## 🔧 Customization

### Adjust Resource Limits

Edit **extreme endpoints** in `organic_web_stress.py`:

```python
# For different CPU load
/extreme/cpu?duration=10&workers=8

# For different memory allocation
/extreme/memory?mb=1024&hold=10

# For different network load
/extreme/all?cpu_duration=10&memory_mb=512&network_mb=200
```

### Adjust Concurrent Users

```bash
# Syntax: command [duration] [users_per_pi]

# Light load: 40 total users (10 per Pi)
./organic_pi_controller.sh extreme-all-99 60 10

# Medium load: 120 total users (30 per Pi)
./organic_pi_controller.sh extreme-all-99 60 30

# Heavy load: 200 total users (50 per Pi)
./organic_pi_controller.sh extreme-all-99 60 50
```

### Modify User Behavior Profiles

Edit `PROFILES` in `organic_traffic_gen.py`:

```python
"custom_user": UserProfile(
    name="Custom User",
    session_duration=(120, 300),  # 2-5 minutes
    pages_per_session=(10, 20),
    think_time=(3, 10),
    endpoints={
        "/": 0.40,
        "/product/{}": 0.30,
        "/checkout": 0.20,
        "/search?q={}": 0.10,
    }
)
```

---

## 🐛 Troubleshooting

### Problem: Pis can't reach server

```bash
# Check connectivity from Pi
ssh alpine-1
ping 192.168.2.50
curl http://192.168.2.50:7777/health
```

### Problem: Traffic generator not starting

```bash
# Check if Python dependencies are installed
ssh alpine-1 "python3 -c 'import aiohttp; print(\"OK\")'"

# Reinstall if needed
./organic_pi_controller.sh install
```

### Problem: Memory stays high after test

```bash
# SSH to server and restart Docker service
ssh your-server
docker service update --force organic-web-stress

# Or scale down and up
docker service scale organic-web-stress=0
sleep 10
docker service scale organic-web-stress=3
```

### Problem: Can't see load distribution

```bash
# Check service logs to see which container handled requests
docker service logs organic-web-stress | grep "X-Server-ID"

# Or check metrics endpoint
curl http://192.168.2.50:7777/metrics | jq
```

---

## 📈 Testing Workflow

### Before Load Balancing

```bash
# 1. Deploy with 1 replica
docker service scale organic-web-stress=1

# 2. Run organic traffic
./organic_pi_controller.sh organic-normal

# 3. Note baseline metrics in Grafana
#    - Response times
#    - CPU/Memory usage
#    - Error rates
```

### After Load Balancing

```bash
# 1. Scale to 3 replicas
docker service scale organic-web-stress=3

# 2. Run same organic traffic
./organic_pi_controller.sh organic-normal

# 3. Compare metrics
#    - Request distribution (should be ~33% each)
#    - Response times (should be lower)
#    - Resource usage (should be distributed)
```

### Extreme Load Testing

```bash
# Test 1: All resources maxed
./organic_pi_controller.sh extreme-all-99 90 35

# Wait for cooldown
sleep 60

# Test 2: CPU + Memory only
./organic_pi_controller.sh extreme-cpu-mem-99 90 35

# Check if load balancer handles it well
./organic_pi_controller.sh distribution
```

---

## 📝 Expected Results

### Organic Traffic

- **Distribution fairness:** ±5% deviation across backends
- **Response times:** Consistent p95 < 500ms
- **User sessions:** Realistic behavior patterns
- **No errors:** < 0.1% error rate

### Extreme Load

- **Resource utilization:** 95-99% on targeted resources
- **Load balancer stability:** Even distribution under stress
- **Recovery:** Quick return to normal after test ends
- **No crashes:** All containers remain healthy

---

## 🎓 Next Steps

1. **Baseline Testing:** Run organic-normal and record metrics
2. **Scale Testing:** Increase replicas and observe distribution
3. **Failure Testing:** Kill one container and watch redistribution
4. **Capacity Planning:** Find breaking point with extreme-all-99
5. **Optimization:** Tune load balancer settings based on results

---

## 📞 Support

For issues or questions about:

- **Web application:** Check `docker service logs organic-web-stress`
- **Traffic generator:** Check logs with `./organic_pi_controller.sh logs`
- **Load balancing:** Verify with `./organic_pi_controller.sh distribution`

Happy testing! 🚀
