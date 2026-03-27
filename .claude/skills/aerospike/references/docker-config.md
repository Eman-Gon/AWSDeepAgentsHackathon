# Aerospike Docker Setup & Configuration

## Quick Start (Development)

```bash
# Pull and run Aerospike CE (Community Edition)
docker run -d --name aerospike \
  -p 3000:3000 \
  -p 3001:3001 \
  -p 3002:3002 \
  -p 3003:3003 \
  aerospike

# Check container is running
docker ps | grep aerospike

# View logs
docker logs aerospike
```

## Port Mapping

| Port | Purpose |
|------|---------|
| 3000 | Client connections (Python client uses this) |
| 3001 | Fabric (inter-node communication) |
| 3002 | Mesh heartbeat |
| 3003 | Info port |

## Default Configuration

In the default Docker image, Aerospike runs with:
- **Storage**: data-in-memory + file backup (`/opt/aerospike/data/`)
- **Namespace**: `test` (default)
- **Memory**: configured via `MEM_GB` env var
- **TTL**: 5 days default (set to 0 for no expiry)

## Custom Configuration

```bash
# Create a custom config
cat > aerospike.conf << 'EOF'
service {
    proto-fd-max 15000
}

logging {
    console {
        context any info
    }
}

network {
    service {
        address any
        port 3000
    }
    heartbeat {
        mode mesh
        port 3002
    }
    fabric {
        port 3001
    }
}

namespace test {
    replication-factor 1
    memory-size 1G
    default-ttl 0
    nsup-period 120
    storage-engine device {
        file /opt/aerospike/data/test.dat
        filesize 4G
        data-in-memory true
    }
}
EOF

# Run with custom config
docker run -d --name aerospike \
  -p 3000:3000 -p 3001:3001 -p 3002:3002 -p 3003:3003 \
  -v $(pwd)/aerospike.conf:/etc/aerospike/aerospike.conf \
  aerospike
```

## Data Persistence

```bash
# Mount a volume for data persistence across container restarts
docker run -d --name aerospike \
  -p 3000:3000 -p 3001:3001 -p 3002:3002 -p 3003:3003 \
  -v aerospike_data:/opt/aerospike/data \
  aerospike
```

## AQL Shell (Interactive Queries)

```bash
# Connect to running Aerospike container
docker run -ti --rm aerospike/aerospike-tools:latest aql \
  -h $(docker inspect -f '{{.NetworkSettings.IPAddress}}' aerospike)

# Or if using host networking
docker run -ti --rm --network host aerospike/aerospike-tools:latest aql -h 127.0.0.1

# Example AQL commands:
# SELECT * FROM test.entities
# SELECT * FROM test.edges WHERE source = 'person_jane_doe'
# INSERT INTO test.entities (PK, name, type) VALUES ('test1', 'Test', 'person')
```

## Docker Compose (for hackathon)

```yaml
version: '3.8'
services:
  aerospike:
    image: aerospike:latest
    container_name: aerospike
    ports:
      - "3000:3000"
      - "3001:3001"
      - "3002:3002"
      - "3003:3003"
    volumes:
      - aerospike_data:/opt/aerospike/data
    environment:
      - NAMESPACE=test
      - MEM_GB=1
      - DEFAULT_TTL=0
    restart: unless-stopped

volumes:
  aerospike_data:
```

## Management Commands

```bash
# Stop container (preserves data if volume mounted)
docker stop aerospike

# Start existing container
docker start aerospike

# Remove container (data lost unless volume mounted)
docker stop aerospike && docker rm aerospike

# Check Aerospike status
docker exec aerospike asinfo -v status
```

## Community Edition Limits

- Max 8 nodes per cluster
- Max 5 TiB of data
- No enterprise features (security, cross-datacenter replication)
- Free for any use including production
