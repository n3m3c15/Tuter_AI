from azure.cosmos import CosmosClient, PartitionKey, DatabaseProxy
from typing import List, Dict, Any

class DictLike:
    def __getitem__(self, key: str) -> Any:
        if hasattr(self, "__dataclass_fields__") and key in getattr(
            self, "__dataclass_fields__", {}
        ):
            return getattr(self, key)
        raise KeyError(f"{key} is not a valid field")

    def __setitem__(self, key: str, value: Any) -> None:
        if hasattr(self, "__dataclass_fields__") and key in getattr(
            self, "__dataclass_fields__", {}
        ):
            setattr(self, key, value)
        else:
            raise KeyError(f"{key} is not a valid field")

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like get method for compatibility with tests that use .get()"""
        try:
            return self[key]
        except KeyError:
            return default

class Usage(DictLike):
    def __init__(self, read_units: float|None = None, write_units: float|None = None):
        if read_units is not None:
            self.readUnits = read_units
        if write_units is not None:
            self.writeUnits = write_units

class UpsertResponse(DictLike):
    def __init__(self, upserted_count: int, usage: Usage|None = None):
        self.upserted_Count = upserted_count
        self.usage = usage  # Placeholder for request charge or usage information

class Vector(DictLike):
    def __init__(self, 
                 id: str, 
                 score: float|None = None, 
                 metadata: Dict[str, Any]|None = None, 
                 values: List[float]|None = None, 
                 namespace: str|None = None):
        self.id = id
        if score:
            self.score = score
        if metadata:
            self.metadata = metadata
        if values:
            self.values = values
        
    def __repr__(self):
        return f"vector({f'score={self.score}' if hasattr(self, 'score') else ''} {f'metadata={self.metadata}' if hasattr(self, 'metadata') else ''})"

class Result(DictLike):
    def __init__(self, 
                 matches: List[Vector]|None = None, 
                 vectors: List[Vector]|None = None, 
                 namespace: str|None = None, 
                 usage: Usage|None = None):
        if matches is None and vectors is not None:
            self.vectors = vectors
        elif matches is not None and vectors is None:
            self.matches = matches
        else:
            raise ValueError("Either matches or vectors must be provided, but not both.")
        self.namespace = namespace
        self.usage = usage  # Placeholder for request charge or usage information
    
    def __repr__(self):
        return f"results({f'matches={self.matches}' if hasattr(self, 'matches') else ''} {f'vectors={self.vectors}' if hasattr(self, 'vectors') else ''})"
    
class CosmosIndex:
    def __init__(self, 
                 database: DatabaseProxy, 
                 container_name: str, 
                 patrition_key: str = "/namespace"):
        self.container = database.get_container_client(container_name)

    def upsert(self, vectors: List[Dict], namespace: str|None = None):
        """
        Upsert embeddings into Cosmos.
        Each item should contain:
        {'vector': list[float], 'metadata': dict, 'namespace': str (optional)}
        """
        for vector in vectors:
            if "namespace" not in vector:
                vector["namespace"] = namespace
            if namespace != vector.get('namespace'):
                raise ValueError(f"Namespace mismatch: expected {namespace}, got {vector.get('namespace')}")
            self.container.upsert_item(vector)
        request_charge = self.container.client_connection.last_response_headers.get('x-ms-request-charge')
        return  UpsertResponse(upserted_count=len(vectors), usage=Usage(write_units=request_charge))

    def query(self, vector: List[float]|None, 
              top_k: int|None = 5, 
              namespace: str|None = None, 
              filter: Dict|None = None, 
              include_metadata: bool = True) -> Result:
        """
        Query Cosmos using native vector search with optional namespace and metadata filters.
        vector: the query embedding
        namespace: filter by namespace (like Pinecone)
        metadata_filter: dict of metadata key-values to filter
        """
        where_clauses = []
        parameters = [{"name": "@values", "value": vector}]

        if namespace:
            where_clauses.append("c.namespace = @namespace")
            parameters.append({"name": "@namespace", "value": namespace})

        if filter:
            for k, v in filter.items():
                if isinstance(v, list):
                    where_clauses.append(f"c.metadata.{k} IN ({', '.join(['@' + k + str(i) for i in range(len(v))])})")
                    parameters.extend([{"name": f"@{k}{i}", "value": v[i]} for i in range(len(v))])
                elif isinstance(v, str):
                    where_clauses.append(f"c.metadata.{k} = @{k}")
                    parameters.append({"name": f"@{k}", "value": v})

        where_text = " AND ".join(where_clauses) if where_clauses else "true"
        select_fields = "c.id, c.values"
        if include_metadata:
            select_fields += ", c.metadata"
        

        query_text = f"""
        SELECT {'TOP ' + str(top_k) if vector and top_k else ''} {select_fields}
        {', VectorDistance(c.values, @values) as score' if vector else ''}
        FROM c
        WHERE {where_text or '1=1'}
        { 'ORDER BY VectorDistance(c.values, @values)' if vector else '' }
        """.strip()

        results = self.container.query_items(
            query=query_text,
            parameters=parameters,
            enable_cross_partition_query=True
        )
        request_charge = self.container.client_connection.last_response_headers.get('x-ms-request-charge')
        return Result(matches = [Vector(id = r['id'], 
                                        score = r['score'], 
                                        values = r['values'], 
                                        metadata = r.get('metadata', {})) for r in results],
                      namespace = namespace,
                      usage = Usage(read_units = request_charge))

    def fetch(self, ids: List[str]|None = None, namespace: str|None = None, include_metadata: bool = True, filter: dict|None = None) -> Result:
        """
        Fetch documents by their IDs with optional namespace filter and metadata inclusion.
        """
        parameters = []
        where_clauses = []
        where_text = ""
        if ids:
            where_clauses = [f"c.id IN ({', '.join(['@id'+str(i) for i in range(len(ids))])})"]
            parameters = [{"name": f"@id{i}", "value": _id} for i, _id in enumerate(ids)]

        if namespace:
            where_clauses.append("c.namespace = @namespace")
            parameters.append({"name": "@namespace", "value": namespace})

        if filter:
            for k, v in filter.items():
                if isinstance(v, list):
                    where_clauses.append(f"c.metadata.{k} IN ({', '.join(['@' + k + str(i) for i in range(len(v))])})")
                    parameters.extend([{"name": f"@{k}{i}", "value": v[i]} for i in range(len(v))])
                elif isinstance(v, str):
                    where_clauses.append(f"c.metadata.{k} = @{k}")
                    parameters.append({"name": f"@{k}", "value": v})

        if where_clauses:
            where_text = " AND ".join(where_clauses)
        select_fields = "c.id, c.values"
        if include_metadata:
            select_fields += ", c.metadata, c.namespace"

        query_text = f"""
            SELECT {select_fields}
            FROM c
            {f'WHERE {where_text}' if where_text else ''}
        """
        all_results = self.container.query_items(
            query=query_text,
            parameters=parameters, # type: ignore
            enable_cross_partition_query=True
        )

        request_charge = self.container.client_connection.last_response_headers.get('x-ms-request-charge')
        return Result(vectors = [Vector(id = r['id'],
                                        values = r['values'],
                                        metadata = r.get('metadata', {})) for r in all_results],
                      namespace = namespace,
                      usage = Usage(read_units = request_charge))
    
    def delete(self, ids: List[str], namespace: str|None = None):
        """
        Delete vectors by their IDs with optional namespace filter.
        """
        if not ids:
            return False
        
        for _id in ids:
            self.container.delete_item(item=_id, partition_key=namespace or "/namespace")
        
        return True  # Indicate successful deletion

class CosmosVectorStore():
    def __init__(self, 
                 endpoint: str, 
                 key: str, 
                 database_name: str):
        self.client = CosmosClient(endpoint, key)
        self.database = self.client.get_database_client(database_name)
    
    def Index(self, container_name: str, partition_key: str = "/namespace"):
        """
        Create a new index for the vector store.
        """
        return CosmosIndex(self.database, container_name, partition_key)