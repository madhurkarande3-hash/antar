"""ANTAR control-room backend.

The pod-side detection logic (antar.detector) is a faithful, testable port of the
detector block in simulation/antar-sim.html. Everything else in this package is the
part that sits *behind the tower*: persistence, alert routing, pod health, and the
live control-room console.
"""
__version__ = "1.0.0"
