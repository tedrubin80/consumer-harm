FROM python:3.12-slim

RUN pip install --no-cache-dir streamlit pandas plotly

WORKDIR /app
COPY harm_themes.py period_config.py paths.py period.env.example ./
COPY dashboard ./dashboard
COPY .streamlit ./.streamlit
COPY deploy/cfpb_summary.db /app/deploy/cfpb_summary.db
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV OPPORTUNITY_HARM_DATA=/data
ENV HOME=/app
ENV PYTHONPATH=/app
ENV PORT=8502

EXPOSE 8502

ENTRYPOINT ["/entrypoint.sh"]
