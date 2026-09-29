"""USDM4 conversion API - a thin HTTP service around a swappable converter.

The service knows one interface (:class:`usdm4_api.converter.Converter`): give it a
protocol PDF, get a USDM 4.0 JSON document back. Everything that reads the protocol lives
behind that interface (today ``usdm4_assure``), so the extraction "brain" can change or be
replaced without touching this package.
"""
