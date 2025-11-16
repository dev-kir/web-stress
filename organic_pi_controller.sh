#!/bin/bash
# Organic Traffic Controller - Control all Alpine Pis from MacBook
# For Docker Swarm Load Balancing Testing

# Configuration
ALPINE_HOSTS="alpine-1 alpine-2 alpine-3 alpine-4"
SERVER="http://192.168.2.50:7777"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }
print_info() { echo -e "${YELLOW}➜${NC} $1"; }

# ==============================
# INSTALLATION
# ==============================

install_deps() {
    print_header "Installing Dependencies on All Pis"
    
    for host in $ALPINE_HOSTS; do
        print_info "Installing on $host..."
        ssh $host "apk add --no-cache python3 py3-pip && \
                   pip3 install aiohttp --break-system-packages" 2>/dev/null
        [ $? -eq 0 ] && print_success "$host: Done" || print_error "$host: Failed"
    done
    echo ""
}

deploy_traffic_gen() {
    print_header "Deploying Traffic Generator to All Pis"
    
    # Check if file exists locally
    if [ ! -f "organic_traffic_gen.py" ]; then
        print_error "organic_traffic_gen.py not found in current directory!"
        echo "Please ensure the file is in the same directory as this script."
        exit 1
    fi
    
    for host in $ALPINE_HOSTS; do
        print_info "Deploying to $host..."
        scp organic_traffic_gen.py $host:/root/ 2>/dev/null
        ssh $host "chmod +x /root/organic_traffic_gen.py" 2>/dev/null
        [ $? -eq 0 ] && print_success "$host: Deployed" || print_error "$host: Failed"
    done
    echo ""
}

# ==============================
# TRAFFIC GENERATION
# ==============================

run_organic_traffic() {
    local users_per_pi=$1
    local duration=$2
    local description=$3
    
    local total_users=$((users_per_pi * 4))
    
    print_header "$description"
    print_info "Duration: ${duration}s"
    print_info "Users per Pi: $users_per_pi (Total: $total_users)"
    print_info "Target: $SERVER"
    echo ""
    
    for host in $ALPINE_HOSTS; do
        print_info "Starting on $host..."
        ssh $host "nohup python3 /root/organic_traffic_gen.py $SERVER --users $users_per_pi --duration $duration > /tmp/traffic_gen.log 2>&1 &" 2>/dev/null
        [ $? -eq 0 ] && print_success "$host: Started" || print_error "$host: Failed"
    done
    
    echo ""
    print_success "Organic traffic running! Total ${total_users} concurrent users"
    print_info "Traffic will run for ${duration} seconds"
    print_info "Watch your Grafana dashboard for load distribution"
    echo ""
}

run_extreme_load() {
    local users_per_pi=$1
    local duration=$2
    local endpoint=$3
    local description=$4
    
    local total_users=$((users_per_pi * 4))
    
    print_header "$description"
    print_info "Duration: ${duration}s"
    print_info "Users per Pi: $users_per_pi (Total: $total_users)"
    print_info "Endpoint: $endpoint"
    echo ""
    
    for host in $ALPINE_HOSTS; do
        print_info "Starting on $host..."
        ssh $host "apk add --no-cache wget 2>/dev/null; \
                   wget -q https://hey-release.s3.us-east-2.amazonaws.com/hey_linux_arm64 -O /usr/local/bin/hey 2>/dev/null; \
                   chmod +x /usr/local/bin/hey 2>/dev/null; \
                   nohup hey -z ${duration}s -c ${users_per_pi} -t 90 '${SERVER}${endpoint}' > /tmp/hey_extreme.log 2>&1 &" 2>/dev/null
        [ $? -eq 0 ] && print_success "$host: Started" || print_error "$host: Failed"
    done
    
    echo ""
    print_success "Extreme load running! Total ${total_users} concurrent users"
    print_info "Expected: ${description}"
    echo ""
}

# ==============================
# STOP & MANAGEMENT
# ==============================

stop_all() {
    print_header "Stopping All Traffic Generators"
    
    for host in $ALPINE_HOSTS; do
        print_info "Stopping on $host..."
        ssh $host "pkill -9 python3; pkill -9 hey" 2>/dev/null
        print_success "$host: Stopped"
    done
    echo ""
}

check_status() {
    print_header "Status Check on All Pis"
    
    for host in $ALPINE_HOSTS; do
        echo -e "${CYAN}--- $host ---${NC}"
        
        # Check Python traffic gen
        py_running=$(ssh $host "ps aux | grep 'organic_traffic_gen.py' | grep -v grep" 2>/dev/null)
        if [ ! -z "$py_running" ]; then
            print_success "Organic traffic generator: Running"
        fi
        
        # Check hey
        hey_running=$(ssh $host "ps aux | grep 'hey' | grep -v grep" 2>/dev/null)
        if [ ! -z "$hey_running" ]; then
            print_success "Extreme load (hey): Running"
        fi
        
        if [ -z "$py_running" ] && [ -z "$hey_running" ]; then
            print_error "No traffic generators running"
        fi
        
        echo ""
    done
}

view_logs() {
    print_header "Recent Logs from All Pis"
    
    for host in $ALPINE_HOSTS; do
        echo -e "${CYAN}--- $host ---${NC}"
        
        echo -e "${YELLOW}Organic Traffic Gen:${NC}"
        ssh $host "tail -15 /tmp/traffic_gen.log 2>/dev/null || echo 'No organic traffic logs'"
        
        echo -e "${YELLOW}Extreme Load (hey):${NC}"
        ssh $host "tail -10 /tmp/hey_extreme.log 2>/dev/null || echo 'No extreme load logs'"
        
        echo ""
    done
}

get_results() {
    print_header "Traffic Generation Results"
    
    for host in $ALPINE_HOSTS; do
        echo -e "${CYAN}--- $host ---${NC}"
        ssh $host "grep -E 'SUMMARY|Total|Successful|Errors|Servers Hit' /tmp/traffic_gen.log 2>/dev/null || \
                   grep -E 'Requests/sec|Total:|Status code' /tmp/hey_extreme.log 2>/dev/null || \
                   echo 'No results yet'"
        echo ""
    done
}

check_server_distribution() {
    print_header "Checking Load Distribution on Target Server"
    
    print_info "Fetching metrics from $SERVER/metrics"
    echo ""
    
    for i in {1..3}; do
        echo -e "${CYAN}Attempt $i:${NC}"
        curl -s "$SERVER/metrics" | python3 -m json.tool 2>/dev/null || echo "Unable to fetch metrics"
        echo ""
        sleep 2
    done
}

# ==============================
# PRE-DEFINED TEST SCENARIOS
# ==============================

# Organic traffic scenarios (realistic user behavior)
organic_normal() {
    run_organic_traffic 15 300 "🌍 ORGANIC: Normal Day Traffic (Realistic User Behavior)"
}

organic_peak() {
    run_organic_traffic 30 300 "🔥 ORGANIC: Peak Hours (High Realistic Traffic)"
}

organic_flash_sale() {
    run_organic_traffic 40 180 "⚡ ORGANIC: Flash Sale Burst (Sudden Traffic Spike)"
}

organic_gradual_ramp() {
    print_header "📈 ORGANIC: Gradual Ramp Up (Staged Increase)"
    
    stages=(
        "10:60:Stage 1 - 40 users"
        "20:60:Stage 2 - 80 users"
        "30:60:Stage 3 - 120 users"
    )
    
    for stage in "${stages[@]}"; do
        IFS=':' read -r users duration desc <<< "$stage"
        print_info "$desc for ${duration}s"
        run_organic_traffic $users $duration "$desc"
        sleep $((duration + 10))
    done
}

# ==============================
# EXTREME LOAD SCENARIOS
# ==============================

# Command 1: 99% ALL Resources (CPU + Memory + Network)
extreme_all_99() {
    local duration=${1:-60}
    local users=${2:-30}
    
    run_extreme_load $users $duration \
        "/extreme/all?cpu_duration=$((duration-5))&memory_mb=512&network_mb=100" \
        "🔴 EXTREME: 99% ALL (CPU + Memory + Network)"
}

# Command 2: 99% CPU + Memory ONLY (Network stays low)
extreme_cpu_mem_99() {
    local duration=${1:-60}
    local users=${2:-35}
    
    run_extreme_load $users $duration \
        "/extreme/cpu-mem?cpu_duration=$((duration-5))&memory_mb=512" \
        "🟠 EXTREME: 99% CPU + Memory (Network Low)"
}

# Additional extreme scenarios
extreme_cpu_only() {
    local duration=${1:-60}
    local users=${2:-40}
    
    run_extreme_load $users $duration \
        "/extreme/cpu?duration=$((duration-5))&workers=6" \
        "🟡 EXTREME: 99% CPU Only"
}

extreme_memory_only() {
    local duration=${1:-60}
    local users=${2:-30}
    
    run_extreme_load $users $duration \
        "/extreme/memory?mb=768&hold=$((duration-5))" \
        "🟢 EXTREME: Memory Saturation"
}

# ==============================
# USAGE & HELP
# ==============================

show_usage() {
    cat << EOF
${BLUE}Organic Traffic Controller v2.0${NC}
${CYAN}For Docker Swarm Load Balancing Testing${NC}

Usage: $0 [command] [options]

${GREEN}=== SETUP COMMANDS ===${NC}
  install               Install dependencies on all Pis
  deploy                Deploy traffic generator to all Pis
  
${GREEN}=== ORGANIC TRAFFIC (Realistic User Behavior) ===${NC}
  organic-normal        Normal day traffic (15 users/Pi = 60 total, 5min)
  organic-peak          Peak hours traffic (30 users/Pi = 120 total, 5min)
  organic-flash-sale    Flash sale burst (40 users/Pi = 160 total, 3min)
  organic-gradual-ramp  Gradual increase in 3 stages (40→80→120 users)

${GREEN}=== EXTREME LOAD (Resource Saturation) ===${NC}
  ${YELLOW}extreme-all-99${NC} [duration] [users]
      99% CPU + Memory + Network together
      Default: 60s, 30 users/Pi (120 total)
      Example: $0 extreme-all-99 90 35
      
  ${YELLOW}extreme-cpu-mem-99${NC} [duration] [users]
      99% CPU + Memory (Network stays LOW)
      Default: 60s, 35 users/Pi (140 total)
      Example: $0 extreme-cpu-mem-99 120 40
      
  extreme-cpu-only [duration] [users]
      99% CPU only (default: 60s, 40 users/Pi)
      
  extreme-memory-only [duration] [users]
      Memory saturation (default: 60s, 30 users/Pi)

${GREEN}=== MANAGEMENT ===${NC}
  stop                  Stop all traffic generators
  status                Check what's running
  logs                  View recent logs
  results               Get traffic generation results
  distribution          Check load distribution across backends

${GREEN}=== DOCKER SWARM DEPLOYMENT ===${NC}
To deploy the web application to Docker Swarm:

  # Build image
  docker build -t your-registry.com/organic-web-stress:1.0 .
  docker push your-registry.com/organic-web-stress:1.0
  
  # Deploy service
  sudo docker service create \\
    --name organic-web-stress \\
    --replicas 3 \\
    --constraint 'node.labels.zone == stress' \\
    --network pymonnet-net \\
    -p 7777:7777 \\
    your-registry.com/organic-web-stress:1.0

${CYAN}=== KEY DIFFERENCES ===${NC}
${YELLOW}Organic Traffic:${NC}
  ✓ Simulates real users (browsing, shopping, searching)
  ✓ Variable think time between requests
  ✓ Mixed endpoint patterns
  ✓ Session-based behavior
  ✓ Best for testing load balancer distribution fairness

${YELLOW}Extreme Load:${NC}
  ✓ Maximum resource utilization (99% CPU/Memory/Network)
  ✓ Tests system limits and breaking points
  ✓ Validates recovery mechanisms
  ✓ Best for stress testing and capacity planning

${CYAN}=== QUICK START ===${NC}
  1. Setup (first time only):
     $0 install
     $0 deploy
     
  2. Run organic traffic test:
     $0 organic-normal
     
  3. Run extreme load test (all resources 99%):
     $0 extreme-all-99 60 30
     
  4. Run extreme load test (CPU+Mem 99%, network low):
     $0 extreme-cpu-mem-99 60 35
     
  5. Check results:
     $0 status
     $0 results
     $0 distribution

${YELLOW}Configuration:${NC}
  Pis: $ALPINE_HOSTS
  Target Server: $SERVER
  
EOF
}

# ==============================
# MAIN LOGIC
# ==============================

case "$1" in
    # Setup
    install)
        install_deps
        ;;
    deploy)
        deploy_traffic_gen
        ;;
    
    # Organic traffic
    organic-normal)
        organic_normal
        ;;
    organic-peak)
        organic_peak
        ;;
    organic-flash-sale)
        organic_flash_sale
        ;;
    organic-gradual-ramp)
        organic_gradual_ramp
        ;;
    
    # Extreme load
    extreme-all-99)
        extreme_all_99 "$2" "$3"
        ;;
    extreme-cpu-mem-99)
        extreme_cpu_mem_99 "$2" "$3"
        ;;
    extreme-cpu-only)
        extreme_cpu_only "$2" "$3"
        ;;
    extreme-memory-only)
        extreme_memory_only "$2" "$3"
        ;;
    
    # Management
    stop)
        stop_all
        ;;
    status)
        check_status
        ;;
    logs)
        view_logs
        ;;
    results)
        get_results
        ;;
    distribution)
        check_server_distribution
        ;;
    
    *)
        show_usage
        exit 1
        ;;
esac