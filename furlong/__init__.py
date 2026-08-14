"""Furlong — a UK horse racing win/place predictor and value finder.

A local, automatic pipeline: scrape Racing Post data (via rpscrape), engineer
leakage-safe form features, train calibrated win models for Flat and Jumps,
derive place / each-way probabilities, and publish a daily HTML dashboard.
"""

__version__ = "0.1.0"
