import argparse

from flow import offline_flow, online_flow


async def run_rag_demo():
    # Sample texts - specialized/fictional content that benefits from RAG
    texts = [
        # Sley framework
        """Sley is an in-process graph runtime for Python and TypeScript.
        Application functions become nodes, links make routing explicit, and Flows
        own local execution scope. Install the Python package with pip install sley
        or the TypeScript package with npm install @jigging/sley.""",
        # Fictional medical device
        """FICTIONAL SAMPLE: NeurAlign M7 is a non-invasive neural alignment device.
        Targeted magnetic resonance technology increases neuroplasticity in specific brain regions.
        Clinical trials showed 72% improvement in PTSD treatment outcomes.
        Developed by Cortex Medical in 2024 as an adjunct to standard cognitive therapy.
        Portable design allows for in-home use with remote practitioner monitoring.""",
        # Made-up historical event
        """FICTIONAL SAMPLE: The Velvet Revolution of Caldonia (1967-1968) ended Generalissimo Verak's 40-year rule.
        Led by poet Eliza Markovian through underground literary societies.
        Culminated in the Great Silence Protest with 300,000 silent protesters.
        First democratic elections held in March 1968 with 94% voter turnout.
        Became a model for non-violent political transitions in neighboring regions.""",
        # Fictional technology
        """FICTIONAL SAMPLE: Q-Mesh is QuantumLeap Technologies' data synchronization protocol.
        Utilizes directed acyclic graph consensus for 500,000 transactions per second.
        Consumes 95% less energy than traditional blockchain systems.
        Adopted by three central banks for secure financial data transfer.
        Released in February 2024 after five years of development in stealth mode.""",
        # Made-up scientific research
        """FICTIONAL SAMPLE: Harlow Institute's Mycelium Strain HI-271 removes PFAS from contaminated soil.
        Engineered fungi create symbiotic relationships with native soil bacteria.
        Breaks down "forever chemicals" into non-toxic compounds within 60 days.
        Field tests successfully remediated previously permanently contaminated industrial sites.
        Deployment costs 80% less than traditional chemical extraction methods.""",
    ]

    print("=" * 50)
    print("Sley RAG Document Retrieval")
    print("=" * 50)

    arguments = argparse.ArgumentParser()
    arguments.add_argument("query", nargs="?", default="How to install Sley?")
    query = arguments.parse_args().query

    state = {
        "texts": texts,
        "embeddings": None,
        "index": None,
        "query": query,
        "query_embedding": None,
        "retrieved_document": None,
        "generated_answer": None,
    }

    state = await offline_flow.run(state)
    return await online_flow.run(state)


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_rag_demo())
