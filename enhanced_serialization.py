"""
Enhanced serialization module for optimized performance with large datasets.
Provides multiple serialization options based on available packages.
"""

import json
import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import logging

logger = logging.getLogger(__name__)

# Try to import optimized JSON libraries
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False
    logger.warning("orjson not available, using standard json")

try:
    import ujson
    HAS_UJSON = True
except ImportError:
    HAS_UJSON = False
    logger.warning("ujson not available, using alternative")

try:
    import msgpack
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False
    logger.warning("msgpack not available, using alternative")

# Serialization format enum
class SerializationFormat(str, Enum):
    JSON = "json"
    ORJSON = "orjson"
    UJSON = "ujson"
    MSGPACK = "msgpack"

# Default serialization format with fallbacks
if HAS_ORJSON:
    DEFAULT_FORMAT = SerializationFormat.ORJSON
elif HAS_UJSON:
    DEFAULT_FORMAT = SerializationFormat.UJSON
else:
    DEFAULT_FORMAT = SerializationFormat.JSON

class EnhancedJSONEncoder(json.JSONEncoder):
    """Enhanced JSON encoder that handles special types."""
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return {"__datetime__": obj.isoformat()}
        elif isinstance(obj, datetime.date):
            return {"__date__": obj.isoformat()}
        elif isinstance(obj, set):
            return {"__set__": list(obj)}
        elif isinstance(obj, bytes):
            return {"__bytes__": obj.decode('utf-8', errors='replace')}
        elif hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
            return obj.to_dict()
        elif hasattr(obj, "__dict__"):
            return obj.__dict__
        return super().default(obj)

def json_decoder_hook(obj):
    """Hook for decoding special types from JSON."""
    if "__datetime__" in obj:
        return datetime.datetime.fromisoformat(obj["__datetime__"])
    elif "__date__" in obj:
        return datetime.date.fromisoformat(obj["__date__"])
    elif "__set__" in obj:
        return set(obj["__set__"])
    elif "__bytes__" in obj:
        return obj["__bytes__"].encode('utf-8')
    return obj

def serialize(data: Any, format: SerializationFormat = DEFAULT_FORMAT) -> bytes:
    """
    Serialize data using the specified format.
    
    Args:
        data: The data to serialize
        format: The serialization format to use
        
    Returns:
        bytes: The serialized data
    """
    if format == SerializationFormat.ORJSON and HAS_ORJSON:
        return orjson.dumps(data, default=EnhancedJSONEncoder().default)
    elif format == SerializationFormat.UJSON and HAS_UJSON:
        return ujson.dumps(data, default=EnhancedJSONEncoder().default).encode('utf-8')
    elif format == SerializationFormat.MSGPACK and HAS_MSGPACK:
        return msgpack.packb(data, default=EnhancedJSONEncoder().default, use_bin_type=True)
    else:
        # Fallback to standard json
        return json.dumps(data, cls=EnhancedJSONEncoder).encode('utf-8')

def deserialize(data: bytes, format: SerializationFormat = DEFAULT_FORMAT) -> Any:
    """
    Deserialize data using the specified format.
    
    Args:
        data: The data to deserialize
        format: The serialization format to use
        
    Returns:
        Any: The deserialized data
    """
    if not data:
        return None
        
    if format == SerializationFormat.ORJSON and HAS_ORJSON:
        return orjson.loads(data, object_hook=json_decoder_hook)
    elif format == SerializationFormat.UJSON and HAS_UJSON:
        return ujson.loads(data.decode('utf-8'), object_hook=json_decoder_hook)
    elif format == SerializationFormat.MSGPACK and HAS_MSGPACK:
        return msgpack.unpackb(data, object_hook=json_decoder_hook, raw=False)
    else:
        # Fallback to standard json
        return json.loads(data.decode('utf-8'), object_hook=json_decoder_hook) 