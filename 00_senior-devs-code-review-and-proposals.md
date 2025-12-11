1. move everything .env file:
    - s3 creds
    - db creds
    - ocr urls
    - llm urls
2. parse the ocr and llm responses right away filtered way, do not store raw files
3. create const.py and move all dictionaries there: one example: latin-to-cyrillic mapping, prompts etc.
   and use this const.py in the code

4. remove circuit breaker
5. remove retry
6. get rid of entrypoint
7. get rid of error_handling 
8. and use fast api's HTTPException
   from fastapi import HTTPException
   he says that no need to handle http exceptions manually if we use fast api's HTTPException ready made exceptions