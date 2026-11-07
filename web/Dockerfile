FROM node:22-alpine AS vendor
WORKDIR /vendor
RUN npm install --no-audit --no-fund ace-builds@1 uplot@1 katex@0 \
    @fontsource/jetbrains-mono@5
# Шрифт вендорится вместе с остальным: страница не должна зависеть от внешней
# сети, а кириллические подмножества у fontsource лежат отдельными файлами.
RUN mkdir -p /out/fonts \
 && cp -r node_modules/@fontsource/jetbrains-mono /out/fonts/jetbrains-mono
RUN mkdir -p /out/ace /out/uplot /out/katex \
 && cp node_modules/ace-builds/src-min-noconflict/ace.js \
       node_modules/ace-builds/src-min-noconflict/mode-python.js \
       node_modules/ace-builds/src-min-noconflict/theme-github_dark.js \
       node_modules/ace-builds/src-min-noconflict/theme-github.js /out/ace/ \
 && cp node_modules/uplot/dist/uPlot.iife.min.js node_modules/uplot/dist/uPlot.min.css /out/uplot/ \
 && cp -r node_modules/katex/dist/katex.min.js node_modules/katex/dist/katex.min.css \
          node_modules/katex/dist/fonts node_modules/katex/dist/contrib/auto-render.min.js /out/katex/

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=vendor /out /app/static/vendor
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
