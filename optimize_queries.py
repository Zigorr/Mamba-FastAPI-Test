"""
Query optimization utilities for SQLAlchemy to improve performance with large datasets.
"""

from sqlalchemy.orm import Query, Session
from sqlalchemy import func, inspect, select
from typing import List, Type, TypeVar, Any, Optional, Dict, Tuple
import logging
from sqlalchemy.sql import expression
from sqlalchemy.ext.compiler import compiles
import time

logger = logging.getLogger(__name__)

T = TypeVar('T')

class QueryStats:
    """Class to track and log query performance statistics"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.query_count = 0
        self.slow_queries = 0
        self.total_time = 0
        self.max_time = 0
        self.min_time = float('inf')
    
    def record_query(self, duration: float):
        self.query_count += 1
        self.total_time += duration
        self.max_time = max(self.max_time, duration)
        self.min_time = min(self.min_time, duration)
        
        if duration > 0.5:  # Queries taking more than 500ms are slow
            self.slow_queries += 1
    
    def get_stats(self) -> Dict[str, Any]:
        if self.query_count == 0:
            return {
                "query_count": 0,
                "avg_time": 0,
                "max_time": 0,
                "min_time": 0,
                "slow_queries": 0
            }
            
        return {
            "query_count": self.query_count,
            "avg_time": self.total_time / self.query_count,
            "max_time": self.max_time,
            "min_time": self.min_time,
            "slow_queries": self.slow_queries
        }
    
    def log_stats(self):
        stats = self.get_stats()
        if stats["query_count"] > 0:
            logger.info(
                f"Query stats: {stats['query_count']} queries, "
                f"avg={stats['avg_time']:.3f}s, "
                f"max={stats['max_time']:.3f}s, "
                f"slow={stats['slow_queries']}"
            )


# Global query stats tracker
query_stats = QueryStats()

# Custom SQL functions

class WithTimeout(expression.FunctionElement):
    """Custom SQL function to set statement timeout."""
    name = "set_timeout"
    type = None

@compiles(WithTimeout)
def _compile_set_timeout_postgresql(element, compiler, **kw):
    """Compile the timeout function for PostgreSQL."""
    return "SET LOCAL statement_timeout = %s" % compiler.process(element.clauses)

def with_timeout(timeout_ms: int):
    """Create a statement timeout clause."""
    return WithTimeout(timeout_ms)

# Query optimization functions

def optimize_count_query(query: Query) -> int:
    """
    Optimize count query by using COUNT() directly in the database.
    
    Args:
        query: SQLAlchemy query object
        
    Returns:
        int: The count result
    """
    start_time = time.time()
    try:
        # Extract only the FROM and WHERE parts from the query
        count_query = query.with_entities(func.count())
        result = count_query.scalar()
        return result
    finally:
        duration = time.time() - start_time
        query_stats.record_query(duration)
        if duration > 0.5:
            logger.warning(f"Slow count query: {duration:.3f}s")

def paginate_query(query: Query, page: int = 1, page_size: int = 20) -> Tuple[List[Any], int, int]:
    """
    Paginate a query with optimized count for large datasets.
    
    Args:
        query: SQLAlchemy query object
        page: Page number (1-based)
        page_size: Number of items per page
        
    Returns:
        Tuple containing:
        - List of items for the page
        - Total count of items
        - Total number of pages
    """
    if page < 1:
        page = 1
    
    # Get the total count with optimized query
    total_count = optimize_count_query(query)
    
    # Calculate total pages
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
    
    # If requested page exceeds total, get last page
    if total_pages > 0 and page > total_pages:
        page = total_pages
    
    # Calculate offset
    offset = (page - 1) * page_size
    
    # Get paginated results
    start_time = time.time()
    try:
        paginated_items = query.limit(page_size).offset(offset).all()
        return paginated_items, total_count, total_pages
    finally:
        duration = time.time() - start_time
        query_stats.record_query(duration)
        if duration > 0.5:
            logger.warning(f"Slow pagination query: {duration:.3f}s")

def bulk_fetch_related(session: Session, model_class: Type[T], ids: List[Any], 
                       related_attribute: str) -> Dict[Any, List[Any]]:
    """
    Efficiently fetch related items for multiple entities in a single query.
    Helps avoid N+1 query problems.
    
    Args:
        session: SQLAlchemy session
        model_class: The model class to fetch related items for
        ids: List of primary key values for the parent entities
        related_attribute: Name of the relationship attribute
        
    Returns:
        Dict mapping parent IDs to lists of related items
    """
    if not ids:
        return {}
    
    mapper = inspect(model_class)
    pk_attr = mapper.primary_key[0].name
    relationship = getattr(mapper.relationships, related_attribute)
    related_model = relationship.mapper.class_
    foreign_key = list(relationship.local_columns)[0].name
    
    start_time = time.time()
    try:
        # Execute a single query to get all related items
        related_items = session.query(related_model).filter(
            getattr(related_model, foreign_key).in_(ids)
        ).all()
        
        # Group by parent ID
        result = {}
        for item in related_items:
            parent_id = getattr(item, foreign_key)
            if parent_id not in result:
                result[parent_id] = []
            result[parent_id].append(item)
        
        # Ensure all requested IDs have an entry, even if empty
        for id_value in ids:
            if id_value not in result:
                result[id_value] = []
        
        return result
    finally:
        duration = time.time() - start_time
        query_stats.record_query(duration)
        if duration > 0.5:
            logger.warning(f"Slow bulk fetch query: {duration:.3f}s for {len(ids)} parent IDs")

def get_query_stats() -> Dict[str, Any]:
    """Get the current query statistics."""
    return query_stats.get_stats()

def reset_query_stats():
    """Reset the query statistics."""
    query_stats.reset() 