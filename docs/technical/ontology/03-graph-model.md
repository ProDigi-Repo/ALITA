# Graph Model (Neo4j)

> The knowledge graph is a Neo4j property graph whose node and relationship types follow DoCO, DEO, FaBiO and CiTO. Code: `backend/app/graph.py`.

## Nodes

| Label | Key | Properties | Ontology |
|---|---|---|---|
| `Document` | `doc_id` | title, doc_type, fabio_type, year, doi, filename, filetype, language, project_name, role, is_latest | FaBiO (`fabio:JournalArticle`, `fabio:Note`, `fabio:WorkPackage`) |
| `Section` | `id` (`doc_id#s<n>`) | heading, order, doc_id | `doco:Section` |
| `Chunk` | `chunk_id` (= Qdrant point id) | ordinal, locator, page, deo, deo_source, doc_id | `doco:Paragraph` |
| `SummaryElement` | `id` (`doc_id#field`) | field, text, source | DEO via mapping |
| `DEOClass` | `name` | uri, definition | `deo:*` (31 classes) |
| `Person` | `name` | | author (PRO role "author") |
| `Database` | `name` | AL, DL, JSW, LDK, ML, UM | ALITA |
| `Project` | `name` | | ALITA (research project) |
| `Method` | `id` | label | ALITA method glossary |
| `Cluster` | `id` | label, title, description | ALITA clustering |
| `Work` | `doi` | | cited or citing publication |
| `Class` | `uri` | | full ontologies imported by n10s (optional) |

## Relationships

| Relationship | Meaning |
|---|---|
| `(Document)-[:CONTAINS {order}]->(Section)-[:CONTAINS {order}]->(Chunk)` | document structure (DoCO `po:contains`) |
| `(Section)`, `(Chunk)`, `(SummaryElement)` `-[:HAS_ROLE]->(DEOClass)` | rhetorical role |
| `(Document)-[:HAS_SUMMARY]->(SummaryElement)` | structured summary |
| `(Person)-[:AUTHORED]->(Document)` | authorship |
| `(Document)-[:IN_DATABASE]->(Database)` | database assignment |
| `(Document)-[:PART_OF]->(Project)` | project files |
| `(Document)-[:USES_METHOD]->(Method)` | method classification |
| `(Document)-[:IN_CLUSTER]->(Cluster)` | semantic cluster |
| `(Document)-[:REPRESENTS]->(Work)` · `(Document)-[:CITES]->(Work)` | own DOI · DOIs found in its bibliography (CiTO) |
| `(DEOClass)-[:SAME_AS]->(Class)` | link to the imported ontology |

## Example queries (Cypher)

Methods sections of LDK papers by an author:

```
MATCH (a:Person)-[:AUTHORED]->(d:Document)-[:IN_DATABASE]->(:Database {name:'LDK'}),
      (d)-[:CONTAINS]->(s:Section)-[:HAS_ROLE]->(:DEOClass {name:'Methods'})
WHERE toLower(a.name) CONTAINS 'leyer'
RETURN d.title, s.heading
```

Which DEO roles occur how often:

```
MATCH (x)-[:HAS_ROLE]->(c:DEOClass) RETURN c.name, labels(x)[0], count(*) ORDER BY count(*) DESC
```

Papers in the collection that cite each other:

```
MATCH (a:Document)-[:CITES]->(w:Work)<-[:REPRESENTS]-(b:Document) RETURN a.title, b.title
```
