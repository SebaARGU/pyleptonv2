from setuptools import setup, find_packages

setup(
    name="lepton",
    version="0.1.0",
    description="Python interface for FLIR Lepton thermal camera (Dev Kit V2)",
    author="LeptonModule",
    packages=find_packages(),
    install_requires=[
        "spidev>=3.5",
        "numpy>=1.21",
    ],
    extras_require={
        "viewer": ["opencv-python>=4.5"],
        "i2c": ["smbus2>=0.4.0"],
    },
    python_requires=">=3.8",
)
