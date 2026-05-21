import os

import dotenv
import neo4j

dotenv.load_dotenv()


def get_neo4j_driver() -> neo4j.Driver:
    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    client_id = os.getenv("NEO4J_CLIENT_ID")
    client_secret = os.getenv("NEO4J_CLIENT_SECRET")
    
    if client_id and client_secret:
        try:
            d = neo4j.GraphDatabase.driver(uri, auth=(client_id, client_secret))
            d.verify_connectivity()
            return d
        except Exception:
            pass
            
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    d = neo4j.GraphDatabase.driver(uri, auth=(username, password))
    d.verify_connectivity()
    return d


if __name__ == "__main__":
    print("Connecting to Neo4j to reset the database...")
    driver = get_neo4j_driver()
    with driver.session() as session:
        # DETACH DELETE n deletes all nodes and their relationships
        result = session.run("MATCH (n) DETACH DELETE n")
        print("Database successfully reset. All nodes and relationships deleted.")
    driver.close()
