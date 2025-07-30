CREATE OR REPLACE MODEL `CustomerReview.Embeddings`
REMOTE WITH CONNECTION `us.embedding_conn`
OPTIONS (ENDPOINT = 'text-embedding-005');

# To upload the dataset from a CSV file, run the following SQL query:

LOAD DATA OVERWRITE CustomerReview.customer_reviews
(
    customer_review_id INT64,
    customer_id INT64,
    location_id INT64,
    review_datetime DATETIME,
    review_text STRING,
    social_media_source STRING,
    social_media_handle STRING
)
FROM FILES (
    format = 'CSV',
    uris = ['gs://spls/gsp1249/customer_reviews.csv']
	
);

#To generate embeddings from recent customer feedback and store them in a table, run the following SQL query in the query ###editor:

CREATE OR REPLACE TABLE `CustomerReview.customer_reviews_embedded` AS
SELECT *
FROM ML.GENERATE_EMBEDDING(
    MODEL `CustomerReview.Embeddings`,
    (SELECT review_text AS content FROM `CustomerReview.customer_reviews`)
);

##To create an index of the vector search space, run the following SQL query:

CREATE OR REPLACE VECTOR INDEX `CustomerReview.reviews_index`
ON `CustomerReview.customer_reviews_embedded`(ml_generate_embedding_result)
OPTIONS (distance_type = 'COSINE', index_type = 'IVF');

# To search the vector space and retrieve the similar items, run the following SQL query:
CREATE OR REPLACE TABLE `CustomerReview.vector_search_result` AS
SELECT
    query.query,
    base.content
FROM
    VECTOR_SEARCH(
        TABLE `CustomerReview.customer_reviews_embedded`,
        'ml_generate_embedding_result',
        (
            SELECT
                ml_generate_embedding_result,
                content AS query
            FROM
                ML.GENERATE_EMBEDDING(
                    MODEL `CustomerReview.Embeddings`,
                    (SELECT 'service' AS content)
                )
        ),
        top_k => 5,
        options => '{"fraction_lists_to_search": 0.01}'
    );

# To connect to the Gemini model, run the following SQL query:
CREATE OR REPLACE MODEL `CustomerReview.Gemini`
REMOTE WITH CONNECTION `us.embedding_conn`
OPTIONS (ENDPOINT = 'gemini-2.0-flash');

#To enhance Gemini's responses, provide it with relevant and recent data retrieved from the vector search by running the following query:

SELECT
    ml_generate_text_llm_result AS generated
FROM
    ML.GENERATE_TEXT(
        MODEL `CustomerReview.Gemini`,
        (
            SELECT
                CONCAT(
                    'Summarize what customers think about our services',
                    STRING_AGG(FORMAT('review text: %s', base.content), ',\n')
                ) AS prompt
            FROM
                `CustomerReview.vector_search_result` AS base
        ),
        STRUCT(
            0.4 AS temperature,
            300 AS max_output_tokens,
            0.5 AS top_p,
            5 AS top_k,
            TRUE AS flatten_json_output
        )
    );