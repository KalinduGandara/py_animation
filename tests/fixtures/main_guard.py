"""Fixture: its ``__main__`` block must not run when loaded by the CLI."""

from bouncekit import Scene

scene = Scene(width=64, height=48, fps=30, duration=0.1)

if __name__ == "__main__":
    raise RuntimeError("__main__ block ran")
