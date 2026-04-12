import torch
import sys

def check_nvidia_gpu():
    print(f"Python Version: {sys.version}")
    print(f"PyTorch Version: {torch.__version__}")
    
    is_available = torch.cuda.is_available()
    print(f"\n[CUDA STATUS] torch.cuda.is_available() = {is_available}")
    
    if is_available:
        gpu_count = torch.cuda.device_count()
        print(f"[CUDA DEVICES] Found {gpu_count} GPU(s).")
        
        for i in range(gpu_count):
            gpu_name = torch.cuda.get_device_name(i)
            print(f"   -> GPU {i}: {gpu_name}")
            
        print("\n✅ SUCCESS: PyTorch is successfully talking to the NVIDIA GPU inside WSL2 Docker!")
    else:
        print("\n❌ FAILED: PyTorch cannot see the GPU. This usually means:")
        print("    1. NVIDIA Container Toolkit is not installed on the Windows Host / WSL2.")
        print("    2. 'deploy.resources.reservations.devices' in docker-compose.yml failed to attach.")
        print("    3. The PyTorch pip installation is the CPU-only version.")

if __name__ == "__main__":
    check_nvidia_gpu()
