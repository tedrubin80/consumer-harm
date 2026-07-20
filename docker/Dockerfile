FROM python:3.12-slim

RUN pip install --no-cache-dir streamlit pandas plotly

WORKDIR /app
COPY harm_themes.py period_config.py paths.py period.env.example ./
COPY dashboard ./dashboard

ENV OPPORTUNITY_HARM_DATA=/data
ENV HOME=/app
ENV PYTHONPATH=/app
ENV PORT=8502

EXPOSE 8502

CMD ["sh", "-c", "exec streamlit run dashboard/app.py --server.port ${PORT} --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false"]
