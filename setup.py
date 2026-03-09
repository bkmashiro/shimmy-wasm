from setuptools import setup, find_packages

setup(
    name="shimmy-wasm",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[],
    entry_points={
        "console_scripts": [
            "shimmy-wasm=src.sandbox:main",
        ],
    },
    python_requires=">=3.8",
    author="Shimmy Team",
    description="WASM-based sandbox for untrusted code execution",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    license="MIT",
)
