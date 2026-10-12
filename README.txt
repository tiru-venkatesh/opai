frontend/  -> copy into opa-main/frontend/ (super-chat.html replaces the old one)
backend/   -> copy feedback_api.py next to main.py, then add to main.py:
    from feedback_api import router as feedback_router
    app.include_router(feedback_router)
requirements.txt: add sqlalchemy
Render env: FEEDBACK_ADMIN_KEY=<your secret>
Admin inbox: feedback.html#admin
