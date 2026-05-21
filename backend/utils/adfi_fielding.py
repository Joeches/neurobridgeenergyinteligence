"""
================================================================================
Project: NeuroBridge 11D Energy Intelligence Kernel
Component: ADFI (Automated Data Fielding Intelligence) - Quantum Enhanced
Version: 3.1.0-QUANTUM-FIXED
Domain: Sovereign Energy Kernel
Description: Enterprise-grade automated data fielding engine for 11D telemetry
             injection with intelligent pattern generation, adaptive fielding,
             real-time streaming, and comprehensive analytics.
FIXED: Windows console encoding compatibility
FIXED: Enhanced error handling for kernel integration
================================================================================
"""

import random
import logging
import httpx
import asyncio
import hashlib
import time
import json
import numpy as np
import platform
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict, field
from collections import deque
from enum import Enum
import uuid

from backend.utils.crypto_lattice import LatticeSecurityEngine

# Windows console encoding fix
if platform.system() == 'Windows':
    try:
        import subprocess
        subprocess.run('chcp 65001 > nul', shell=True, capture_output=True)
    except:
        pass

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logger = logging.getLogger("NeuroBridge.ADFI")

# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class ADFIPattern(Enum):
    """ADFI data generation patterns"""
    NORMAL = "normal"
    SPIKE = "spike"
    DRIFT = "drift"
    ANOMALY = "anomaly"
    STRESS = "stress"
    SEASONAL = "seasonal"
    RANDOM_WALK = "random_walk"
    SINUSOIDAL = "sinusoidal"

class ADFIPriority(Enum):
    """ADFI packet priority levels"""
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3

class DataQuality(Enum):
    """Data quality classifications"""
    EXCELLENT = 0.98
    GOOD = 0.92
    FAIR = 0.85
    POOR = 0.70
    DEGRADED = 0.50


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ADFITelemetryPacket:
    """Comprehensive telemetry packet with 11D metadata"""
    packet_id: str
    sensor_id: str
    thermal_load: float
    vibration_hz: float
    ergotropy_flux: float
    grid_frequency: float
    structural_stability: float
    hardware_hash: str
    timestamp: str
    confidence_score: float
    quality_score: float
    data_source: str
    pattern_type: str
    priority: ADFIPriority
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        result['priority'] = self.priority.value
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), default=str)


@dataclass
class ADFIBatchResult:
    """Batch injection results"""
    batch_id: str
    total_packets: int
    successful: int
    failed: int
    avg_quality: float
    avg_confidence: float
    generation_time_ms: float
    packets_per_second: float
    timestamp: str
    details: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ADFISimulationConfig:
    """Configuration for ADFI simulations"""
    sector: str = "energy_grid"
    pattern: ADFIPattern = ADFIPattern.NORMAL
    count: int = 1
    interval_seconds: float = 1.0
    priority: ADFIPriority = ADFIPriority.MEDIUM
    inject_to_backend: bool = True
    base_url: str = "http://127.0.0.1:8000"
    use_quantum_kernel: bool = True  # NEW: Enable quantum kernel integration
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sector": self.sector,
            "pattern": self.pattern.value,
            "count": self.count,
            "interval_seconds": self.interval_seconds,
            "priority": self.priority.value,
            "inject_to_backend": self.inject_to_backend,
            "use_quantum_kernel": self.use_quantum_kernel
        }


# ============================================================================
# PATTERN GENERATORS
# ============================================================================

class PatternGenerator:
    """Advanced pattern generation for realistic telemetry"""
    
    @staticmethod
    def normal(mean: float = 0, std: float = 1) -> float:
        """Generate normal distribution value"""
        return np.random.normal(mean, std)
    
    @staticmethod
    def spike(amplitude: float = 1.5, probability: float = 0.1) -> float:
        """Generate spike pattern"""
        return amplitude if random.random() < probability else 1.0
    
    @staticmethod
    def drift(start: float, end: float, step: int, total_steps: int) -> float:
        """Generate drift pattern over time"""
        progress = step / max(1, total_steps)
        return start + (end - start) * progress
    
    @staticmethod
    def seasonal(hour: int, amplitude: float = 0.3) -> float:
        """Generate seasonal/day pattern"""
        return amplitude * np.sin(2 * np.pi * hour / 24)
    
    @staticmethod
    def random_walk(step: int, volatility: float = 0.1) -> float:
        """Generate random walk pattern"""
        return np.random.randn() * volatility * np.sqrt(step)
    
    @staticmethod
    def sinusoidal(amplitude: float, frequency: float, phase: float = 0) -> float:
        """Generate sinusoidal pattern"""
        return amplitude * np.sin(2 * np.pi * frequency * time.time() + phase)


# ============================================================================
# MAIN ADFI ORCHESTRATOR
# ============================================================================

class ADFIOrchestrator:
    """
    Enterprise-grade ADFI Orchestrator with intelligent pattern generation,
    real-time analytics, and comprehensive data fielding capabilities.
    """
    
    # Abuja Grid Reference Coordinates
    ABUJA_COORDINATES = {"lat": 9.0765, "lon": 7.3986}
    
    # Sensor profiles with baselines
    SENSOR_PROFILES = {
        "ABJ-GRID-01": {"zone": "Alpha Core", "priority": ADFIPriority.HIGH, "baseline_temp": 32.5, "baseline_vib": 50.0},
        "ABJ-GRID-02": {"zone": "Beta District", "priority": ADFIPriority.MEDIUM, "baseline_temp": 31.0, "baseline_vib": 48.5},
        "ABJ-GRID-03": {"zone": "Gamma Industrial", "priority": ADFIPriority.HIGH, "baseline_temp": 35.0, "baseline_vib": 52.0},
        "ABJ-GRID-04": {"zone": "Delta Residential", "priority": ADFIPriority.MEDIUM, "baseline_temp": 30.5, "baseline_vib": 49.0},
        "ABJ-GRID-05": {"zone": "Epsilon Commercial", "priority": ADFIPriority.LOW, "baseline_temp": 31.5, "baseline_vib": 50.5}
    }
    
    # Pattern configurations
    PATTERN_CONFIGS = {
        ADFIPattern.NORMAL: {
            "temp_range": (-2, 2),
            "vib_range": (-1, 1),
            "ergo_range": (-15, 15),
            "conf_range": (0.92, 0.98),
            "quality_range": (0.90, 0.96)
        },
        ADFIPattern.SPIKE: {
            "temp_range": (5, 15),
            "vib_range": (10, 30),
            "ergo_range": (50, 100),
            "conf_range": (0.75, 0.85),
            "quality_range": (0.70, 0.82)
        },
        ADFIPattern.DRIFT: {
            "temp_range": (3, 8),
            "vib_range": (5, 15),
            "ergo_range": (20, 40),
            "conf_range": (0.80, 0.90),
            "quality_range": (0.78, 0.88)
        },
        ADFIPattern.ANOMALY: {
            "temp_range": (15, 25),
            "vib_range": (20, 50),
            "ergo_range": (80, 120),
            "conf_range": (0.50, 0.70),
            "quality_range": (0.45, 0.65)
        },
        ADFIPattern.STRESS: {
            "temp_range": (8, 18),
            "vib_range": (15, 40),
            "ergo_range": (40, 80),
            "conf_range": (0.60, 0.80),
            "quality_range": (0.55, 0.75)
        },
        ADFIPattern.SEASONAL: {
            "temp_range": (-5, 5),
            "vib_range": (-2, 2),
            "ergo_range": (-20, 20),
            "conf_range": (0.88, 0.95),
            "quality_range": (0.85, 0.93)
        },
        ADFIPattern.RANDOM_WALK: {
            "temp_range": (-4, 4),
            "vib_range": (-3, 3),
            "ergo_range": (-30, 30),
            "conf_range": (0.82, 0.92),
            "quality_range": (0.80, 0.90)
        },
        ADFIPattern.SINUSOIDAL: {
            "temp_range": (-6, 6),
            "vib_range": (-4, 4),
            "ergo_range": (-25, 25),
            "conf_range": (0.85, 0.94),
            "quality_range": (0.82, 0.92)
        }
    }
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000", kernel=None):
        """
        Initialize the ADFI Orchestrator with enhanced capabilities.
        
        Args:
            base_url: Base URL for backend API
            kernel: Optional quantum kernel reference
        """
        self.base_url = base_url
        self.engine = LatticeSecurityEngine()
        self._session_code: Optional[str] = None
        self._historical_data: deque = deque(maxlen=10000)
        self._packet_history: List[ADFITelemetryPacket] = []
        self._total_generated: int = 0
        self._total_injected: int = 0
        self._total_failed: int = 0
        self._start_time: datetime = datetime.now(timezone.utc)
        self._pattern_generator = PatternGenerator()
        self._kernel = kernel
        
        # Time-of-day patterns for Abuja
        self._time_patterns = {
            "peak_hours": (10, 18, 1.3, 1.2),
            "off_peak": (0, 6, 0.7, 0.8),
            "normal": (6, 10, 1.0, 1.0),
            "evening": (18, 22, 1.15, 1.1),
            "night": (22, 24, 0.8, 0.85)
        }
        
        # Use ASCII-only log messages for Windows compatibility
        if platform.system() == 'Windows':
            logger.info("[ROCKET] ADFI Orchestrator v3.1.0 initialized")
            logger.info(f"[ANT] Backend URL: {base_url}")
            logger.info(f"[TARGET] Available patterns: {[p.value for p in ADFIPattern]}")
            logger.info(f"[PLUG] Sensor profiles loaded: {len(self.SENSOR_PROFILES)}")
        else:
            logger.info("🚀 ADFI Orchestrator v3.1.0 initialized")
            logger.info(f"📡 Backend URL: {base_url}")
            logger.info(f"🎯 Available patterns: {[p.value for p in ADFIPattern]}")
            logger.info(f"🔌 Sensor profiles loaded: {len(self.SENSOR_PROFILES)}")
    
    def set_kernel(self, kernel):
        """Set quantum kernel reference"""
        self._kernel = kernel
        if platform.system() == 'Windows':
            logger.info("[BRAIN] Quantum kernel attached to ADFI")
        else:
            logger.info("🧠 Quantum kernel attached to ADFI")
    
    def _get_time_factor(self) -> Tuple[float, float]:
        """Calculate time-of-day factors for Abuja"""
        hour = datetime.now(timezone.utc).hour + 1  # UTC+1 for Abuja
        for pattern in self._time_patterns.values():
            if pattern[0] <= hour < pattern[1]:
                return pattern[2], pattern[3]
        return 1.0, 1.0
    
    def _generate_hardware_hash(self, sensor_id: str) -> str:
        """Generate secure hardware hash"""
        timestamp = int(time.time() * 1000)
        unique_id = f"{sensor_id}_{timestamp}_{uuid.uuid4().hex[:8]}"
        hash_digest = hashlib.sha3_512(unique_id.encode()).hexdigest()[:24]
        return f"sha3_{hash_digest}_SOVEREIGN"
    
    def _calculate_quality_score(self, pattern: ADFIPattern, values: Dict[str, float]) -> float:
        """Calculate data quality score based on pattern and values"""
        config = self.PATTERN_CONFIGS.get(pattern, self.PATTERN_CONFIGS[ADFIPattern.NORMAL])
        base_quality = random.uniform(*config["quality_range"])
        
        # Adjust based on deviation from normal
        temp_deviation = abs(values.get('thermal_load', 32.5) - 32.5) / 10
        vib_deviation = abs(values.get('vibration_hz', 50.0) - 50.0) / 20
        quality_penalty = (temp_deviation + vib_deviation) * 0.05
        
        return max(0.3, min(0.99, base_quality - quality_penalty))
    
    def _apply_quantum_kernel(self, packet: ADFITelemetryPacket) -> ADFITelemetryPacket:
        """
        Apply quantum kernel optimization to packet data.
        Uses the kernel's calculate_yield_ergotropy with proper float arguments.
        """
        if not self._kernel:
            return packet
        
        try:
            # FIXED: Pass two float arguments to kernel
            input_energy = packet.ergotropy_flux  # float
            entropy_loss = 0.05  # float
            
            kernel_yield = self._kernel.calculate_yield_ergotropy(input_energy, entropy_loss)
            
            if kernel_yield and kernel_yield > 0:
                packet.ergotropy_flux = round(kernel_yield, 2)
                packet.confidence_score = min(0.99, packet.confidence_score + 0.05)
                packet.metadata["quantum_enhanced"] = True
                
                if platform.system() == 'Windows':
                    logger.debug(f"[QUANTUM] Kernel applied: {input_energy:.2f} -> {kernel_yield:.2f}")
                else:
                    logger.debug(f"⚛️ Kernel applied: {input_energy:.2f} -> {kernel_yield:.2f}")
                
        except TypeError as te:
            logger.error(f"TypeError in kernel call: {te}")
            logger.error(f"Expected float, float | Got: {type(input_energy)}, {type(entropy_loss)}")
        except AttributeError as ae:
            logger.error(f"Kernel attribute error: {ae}")
        except Exception as e:
            logger.warning(f"Kernel error during ADFI generation: {e}")
        
        return packet
    
    def _generate_packet(
        self,
        sensor_id: str,
        pattern: ADFIPattern,
        packet_index: int,
        step: int = 0,
        total_steps: int = 1,
        use_quantum: bool = True
    ) -> ADFITelemetryPacket:
        """
        Generate a single telemetry packet with realistic physics.
        
        Args:
            sensor_id: Target sensor ID
            pattern: Generation pattern
            packet_index: Packet sequence number
            step: Current step for drift patterns
            total_steps: Total steps for drift patterns
            use_quantum: Whether to apply quantum kernel optimization
            
        Returns:
            Generated telemetry packet
        """
        profile = self.SENSOR_PROFILES.get(sensor_id, self.SENSOR_PROFILES["ABJ-GRID-01"])
        config = self.PATTERN_CONFIGS.get(pattern, self.PATTERN_CONFIGS[ADFIPattern.NORMAL])
        time_factor, vib_time_factor = self._get_time_factor()
        
        # Base values
        base_temp = profile["baseline_temp"]
        base_vib = profile["baseline_vib"]
        base_ergo = 120.0
        base_freq = 50.0
        base_stability = 98.0
        
        # Apply pattern-specific modifications
        if pattern == ADFIPattern.NORMAL:
            temp_offset = random.uniform(*config["temp_range"])
            vib_offset = random.uniform(*config["vib_range"])
            ergo_offset = random.uniform(*config["ergo_range"])
            
        elif pattern == ADFIPattern.SPIKE:
            spike_intensity = random.uniform(1.2, 2.0)
            temp_offset = random.uniform(*config["temp_range"]) * spike_intensity
            vib_offset = random.uniform(*config["vib_range"]) * spike_intensity
            ergo_offset = random.uniform(*config["ergo_range"]) * spike_intensity
            
        elif pattern == ADFIPattern.DRIFT:
            progress = step / max(1, total_steps)
            temp_offset = random.uniform(*config["temp_range"]) * progress
            vib_offset = random.uniform(*config["vib_range"]) * progress
            ergo_offset = random.uniform(*config["ergo_range"]) * progress
            
        elif pattern == ADFIPattern.SEASONAL:
            hour = datetime.now().hour
            temp_offset = random.uniform(*config["temp_range"]) * PatternGenerator.seasonal(hour)
            vib_offset = random.uniform(*config["vib_range"]) * PatternGenerator.seasonal(hour)
            ergo_offset = random.uniform(*config["ergo_range"]) * PatternGenerator.seasonal(hour)
            
        elif pattern == ADFIPattern.RANDOM_WALK:
            temp_offset = random.uniform(*config["temp_range"]) * PatternGenerator.random_walk(step)
            vib_offset = random.uniform(*config["vib_range"]) * PatternGenerator.random_walk(step)
            ergo_offset = random.uniform(*config["ergo_range"]) * PatternGenerator.random_walk(step)
            
        elif pattern == ADFIPattern.SINUSOIDAL:
            temp_offset = random.uniform(*config["temp_range"]) * PatternGenerator.sinusoidal(1, 0.1)
            vib_offset = random.uniform(*config["vib_range"]) * PatternGenerator.sinusoidal(1, 0.2)
            ergo_offset = random.uniform(*config["ergo_range"]) * PatternGenerator.sinusoidal(1, 0.05)
            
        else:  # ANOMALY or STRESS
            temp_offset = random.uniform(*config["temp_range"])
            vib_offset = random.uniform(*config["vib_range"])
            ergo_offset = random.uniform(*config["ergo_range"])
        
        # Apply time factors
        temp_offset *= time_factor
        vib_offset *= vib_time_factor
        
        # Calculate final values
        thermal_load = round(base_temp + temp_offset, 2)
        vibration_hz = round(base_vib + vib_offset, 2)
        ergotropy_flux = round(base_ergo + ergo_offset, 2)
        grid_frequency = round(base_freq + random.uniform(-0.3, 0.3), 3)
        structural_stability = round(base_stability - abs(temp_offset) * 0.3, 2)
        
        # Confidence and quality
        confidence = random.uniform(*config["conf_range"])
        values = {"thermal_load": thermal_load, "vibration_hz": vibration_hz}
        quality = self._calculate_quality_score(pattern, values)
        
        # Create packet
        packet = ADFITelemetryPacket(
            packet_id=f"ADFI-{sensor_id}-{packet_index}-{int(time.time() * 1000)}",
            sensor_id=sensor_id,
            thermal_load=thermal_load,
            vibration_hz=vibration_hz,
            ergotropy_flux=ergotropy_flux,
            grid_frequency=grid_frequency,
            structural_stability=structural_stability,
            hardware_hash=self._generate_hardware_hash(sensor_id),
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence_score=round(confidence, 3),
            quality_score=round(quality, 3),
            data_source="ADFI_GENERATOR",
            pattern_type=pattern.value,
            priority=profile["priority"],
            metadata={
                "zone": profile["zone"],
                "pattern_step": step,
                "total_steps": total_steps,
                "abuja_coordinates": self.ABUJA_COORDINATES
            }
        )
        
        # Apply quantum kernel if enabled
        if use_quantum and self._kernel:
            packet = self._apply_quantum_kernel(packet)
        
        return packet
    
    async def generate_packets(
        self,
        config: ADFISimulationConfig
    ) -> ADFIBatchResult:
        """
        Generate telemetry packets based on configuration.
        
        Args:
            config: Simulation configuration
            
        Returns:
            Batch result with generated packets
        """
        start_time = time.time()
        batch_id = f"BATCH-{uuid.uuid4().hex[:8]}-{int(time.time())}"
        packets = []
        successful = 0
        failed = 0
        
        if platform.system() == 'Windows':
            logger.info(f"[TARGET] Generating {config.count} packets for {config.sector} with pattern {config.pattern.value}")
        else:
            logger.info(f"🎯 Generating {config.count} packets for {config.sector} with pattern {config.pattern.value}")
        
        for i in range(config.count):
            try:
                # Select sensor
                sensor_id = random.choice(list(self.SENSOR_PROFILES.keys()))
                
                # Generate packet
                packet = self._generate_packet(
                    sensor_id=sensor_id,
                    pattern=config.pattern,
                    packet_index=i + 1,
                    step=i,
                    total_steps=config.count,
                    use_quantum=config.use_quantum_kernel
                )
                
                packets.append(packet)
                self._packet_history.append(packet)
                self._total_generated += 1
                successful += 1
                
                # Optionally inject to backend
                if config.inject_to_backend:
                    await self._inject_packet(packet)
                    self._total_injected += 1
                
                # Log progress
                if (i + 1) % 10 == 0:
                    logger.debug(f"Generated {i + 1}/{config.count} packets")
                
                # Respect interval
                if config.interval_seconds > 0 and i < config.count - 1:
                    await asyncio.sleep(config.interval_seconds)
                    
            except Exception as e:
                logger.error(f"Packet generation failed: {e}")
                failed += 1
                self._total_failed += 1
        
        generation_time = (time.time() - start_time) * 1000
        avg_quality = sum(p.quality_score for p in packets) / max(1, len(packets))
        avg_confidence = sum(p.confidence_score for p in packets) / max(1, len(packets))
        
        result = ADFIBatchResult(
            batch_id=batch_id,
            total_packets=config.count,
            successful=successful,
            failed=failed,
            avg_quality=round(avg_quality, 3),
            avg_confidence=round(avg_confidence, 3),
            generation_time_ms=round(generation_time, 2),
            packets_per_second=round(config.count / (generation_time / 1000), 2),
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=[p.to_dict() for p in packets[:10]]  # Limit details
        )
        
        if platform.system() == 'Windows':
            logger.info(f"[OK] Batch {batch_id} complete: {successful}/{config.count} successful")
        else:
            logger.info(f"✅ Batch {batch_id} complete: {successful}/{config.count} successful")
        return result
    
    async def _inject_packet(self, packet: ADFITelemetryPacket) -> bool:
        """
        Inject a single packet into the backend.
        
        Args:
            packet: Telemetry packet to inject
            
        Returns:
            Success status
        """
        try:
            # Get or provision session
            if not self._session_code:
                code, _ = self.engine.provision_access()
                self._session_code = code
            
            headers = {"Authorization": f"Bearer {self._session_code}"}
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/sensors/ingest",
                    json=packet.to_dict(),
                    headers=headers
                )
                
                if response.status_code == 200:
                    logger.debug(f"[OK] Injected packet {packet.packet_id}")
                    return True
                else:
                    logger.warning(f"[WARN] Injection failed: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"[X] Injection error: {e}")
            return False
    
    async def field_data_automatically(
        self,
        count: int = 1,
        sector: str = "energy_grid",
        pattern: str = "normal",
        use_quantum: bool = True
    ) -> Dict[str, Any]:
        """
        Public method for automated data fielding.
        
        Args:
            count: Number of packets to generate
            sector: Target sector
            pattern: Data pattern
            use_quantum: Whether to use quantum kernel
            
        Returns:
            Generation results
        """
        # Map pattern string to enum
        try:
            pattern_enum = ADFIPattern(pattern.lower())
        except ValueError:
            pattern_enum = ADFIPattern.NORMAL
        
        config = ADFISimulationConfig(
            sector=sector,
            pattern=pattern_enum,
            count=min(count, 100),  # Limit to 100
            interval_seconds=0.1,
            inject_to_backend=True,
            use_quantum_kernel=use_quantum
        )
        
        result = await self.generate_packets(config)
        
        return {
            "status": "SUCCESS",
            "packets_generated": result.total_packets,
            "sector": sector,
            "pattern": pattern,
            "quality_score": result.avg_quality,
            "avg_confidence": result.avg_confidence,
            "generation_time_ms": result.generation_time_ms,
            "packets_per_second": result.packets_per_second,
            "quantum_enhanced": use_quantum and self._kernel is not None,
            "timestamp": result.timestamp
        }
    
    async def run_stress_test(
        self,
        sector: str = "energy_grid",
        duration_seconds: int = 30,
        target_rate: int = 10,
        use_quantum: bool = True
    ) -> Dict[str, Any]:
        """
        Run high-frequency stress test.
        
        Args:
            sector: Target sector
            duration_seconds: Test duration
            target_rate: Target packets per second
            use_quantum: Whether to use quantum kernel
            
        Returns:
            Stress test results
        """
        start_time = time.time()
        total_packets = 0
        successful = 0
        failed = 0
        latencies = []
        
        end_time = start_time + duration_seconds
        
        if platform.system() == 'Windows':
            logger.info(f"[FIRE] Starting stress test: {duration_seconds}s @ {target_rate} pps")
        else:
            logger.info(f"🔥 Starting stress test: {duration_seconds}s @ {target_rate} pps")
        
        while time.time() < end_time:
            batch_start = time.time()
            
            try:
                result = await self.field_data_automatically(
                    count=target_rate,
                    sector=sector,
                    pattern="stress",
                    use_quantum=use_quantum
                )
                
                total_packets += result["packets_generated"]
                successful += result["packets_generated"]
                latencies.append(result["generation_time_ms"])
                
            except Exception as e:
                logger.error(f"Stress test batch error: {e}")
                failed += target_rate
            
            # Maintain rate
            elapsed = time.time() - batch_start
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
        
        duration = time.time() - start_time
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        throughput = total_packets / duration if duration > 0 else 0
        success_rate = (successful / max(1, total_packets)) * 100
        
        if platform.system() == 'Windows':
            logger.info(f"[OK] Stress test complete: {total_packets} packets, {success_rate:.1f}% success")
        else:
            logger.info(f"✅ Stress test complete: {total_packets} packets, {success_rate:.1f}% success")
        
        return {
            "duration_seconds": round(duration, 2),
            "total_packets": total_packets,
            "successful": successful,
            "failed": failed,
            "avg_latency_ms": round(avg_latency, 2),
            "throughput_pps": round(throughput, 2),
            "success_rate": round(success_rate, 2),
            "quantum_enhanced": use_quantum,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive ADFI statistics"""
        uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()
        
        return {
            "service": "ADFI Orchestrator",
            "version": "3.1.0-QUANTUM-FIXED",
            "status": "OPERATIONAL",
            "uptime_seconds": round(uptime, 2),
            "total_generated": self._total_generated,
            "total_injected": self._total_injected,
            "total_failed": self._total_failed,
            "success_rate": round(self._total_injected / max(1, self._total_generated) * 100, 2),
            "history_size": len(self._packet_history),
            "available_patterns": [p.value for p in ADFIPattern],
            "sensor_profiles": list(self.SENSOR_PROFILES.keys()),
            "active_session": self._session_code is not None,
            "quantum_kernel_attached": self._kernel is not None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def continuous_streaming(self, interval_seconds: float = 5.0, use_quantum: bool = True):
        """
        Generator for continuous ADFI data streaming.
        
        Args:
            interval_seconds: Time between data points
            use_quantum: Whether to use quantum kernel
        """
        if platform.system() == 'Windows':
            logger.info(f"[ANT] Starting continuous streaming (interval: {interval_seconds}s)")
        else:
            logger.info(f"📡 Starting continuous streaming (interval: {interval_seconds}s)")
        
        while True:
            try:
                config = ADFISimulationConfig(
                    pattern=ADFIPattern.NORMAL,
                    count=1,
                    interval_seconds=0,
                    inject_to_backend=True,
                    use_quantum_kernel=use_quantum
                )
                
                result = await self.generate_packets(config)
                
                if result.details:
                    yield result.details[0]
                    
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                
            await asyncio.sleep(interval_seconds)
    
    def reset(self) -> Dict[str, Any]:
        """Reset ADFI statistics and history"""
        self._historical_data.clear()
        self._packet_history.clear()
        self._total_generated = 0
        self._total_injected = 0
        self._total_failed = 0
        self._start_time = datetime.now(timezone.utc)
        
        if platform.system() == 'Windows':
            logger.info("[SYNC] ADFI statistics reset")
        else:
            logger.info("🔄 ADFI statistics reset")
        
        return {
            "status": "SUCCESS",
            "message": "ADFI statistics reset",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def stop(self):
        """Graceful shutdown of ADFI orchestrator"""
        if platform.system() == 'Windows':
            logger.info("[STOP] ADFI Orchestrator shutting down")
        else:
            logger.info("🛑 ADFI Orchestrator shutting down")
        self._session_code = None
        self._packet_history.clear()
        
    async def on_hardware_telemetry(self, telemetry):
        """Handle incoming hardware telemetry for ADFI processing"""
        logger.debug(f"Hardware telemetry received: {telemetry.get('packet_id', 'unknown')}")


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

_adfi_instance: Optional[ADFIOrchestrator] = None

def get_adfi_orchestrator(base_url: str = "http://127.0.0.1:8000", kernel=None) -> ADFIOrchestrator:
    """Get or create ADFI orchestrator instance"""
    global _adfi_instance
    if _adfi_instance is None:
        _adfi_instance = ADFIOrchestrator(base_url, kernel)
    elif kernel and _adfi_instance._kernel is None:
        _adfi_instance.set_kernel(kernel)
    return _adfi_instance


# ============================================================================
# STANDALONE TESTING
# ============================================================================

if __name__ == "__main__":
    import asyncio
    
    async def test_adfi():
        """Test ADFI functionality"""
        print("\n" + "="*80)
        print("  ADFI ORCHESTRATOR TEST SUITE")
        print("  NeuroBridge 11D Quantum Intelligence")
        print("="*80)
        
        # Create mock kernel for testing
        class MockKernel:
            def calculate_yield_ergotropy(self, input_energy: float, entropy_loss: float) -> float:
                return input_energy * (1 - entropy_loss)
        
        orchestrator = get_adfi_orchestrator(kernel=MockKernel())
        
        # Test 1: Basic generation
        print("\n[TEST] 1: Basic Packet Generation")
        result = await orchestrator.field_data_automatically(count=3, pattern="normal")
        print(f"  Generated: {result['packets_generated']} packets")
        print(f"  Quality: {result['quality_score']}")
        print(f"  Quantum Enhanced: {result['quantum_enhanced']}")
        print(f"  Time: {result['generation_time_ms']}ms")
        
        # Test 2: Pattern variations with quantum
        print("\n[TEST] 2: Pattern Variations with Quantum")
        for pattern in ["normal", "spike", "drift", "anomaly"]:
            result = await orchestrator.field_data_automatically(count=2, pattern=pattern, use_quantum=True)
            print(f"  {pattern.upper():12} | Quality: {result['quality_score']} | Confidence: {result['avg_confidence']}")
        
        # Test 3: Statistics
        print("\n[TEST] 3: Service Statistics")
        stats = orchestrator.get_statistics()
        print(f"  Total Generated: {stats['total_generated']}")
        print(f"  Success Rate: {stats['success_rate']}%")
        print(f"  Quantum Kernel: {stats['quantum_kernel_attached']}")
        print(f"  Uptime: {stats['uptime_seconds']:.0f}s")
        
        print("\n" + "="*80)
        print("  [OK] ADFI Test Complete")
        print("="*80 + "\n")
    
    asyncio.run(test_adfi())