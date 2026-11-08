FROM node:22-alpine AS vendor
WORKDIR /vendor
RUN npm install --no-audit --no-fund ace-builds@1 uplot@1 katex@0 \
    @fontsource/jetbrains-mono@5 @fontsource-variable/inter@5 \
    tailwindcss@4 @tailwindcss/cli@4 @tailwindcss/typography@0.5
# Шрифт вендорится вместе с остальным: страница не должна зависеть от внешней
# сети, а кириллические подмножества у fontsource лежат отдельными файлами.
RUN mkdir -p /out/fonts \
 && cp -r node_modules/@fontsource/jetbrains-mono /out/fonts/jetbrains-mono \
 && cp -r node_modules/@fontsource-variable/inter /out/fonts/inter
RUN mkdir -p /out/ace /out/uplot /out/katex \
 && cp node_modules/ace-builds/src-min-noconflict/ace.js \
       node_modules/ace-builds/src-min-noconflict/mode-python.js \
       node_modules/ace-builds/src-min-noconflict/mode-protobuf.js \
       node_modules/ace-builds/src-min-noconflict/theme-github_dark.js \
       node_modules/ace-builds/src-min-noconflict/theme-github.js /out/ace/ \
 && cp node_modules/uplot/dist/uPlot.iife.min.js node_modules/uplot/dist/uPlot.min.css /out/uplot/ \
 && cp -r node_modules/katex/dist/katex.min.js node_modules/katex/dist/katex.min.css \
          node_modules/katex/dist/fonts node_modules/katex/dist/contrib/auto-render.min.js /out/katex/
# Стили собираются из исходников страницы: Tailwind оставляет в app.css только
# те утилиты, которые нашёл в шаблонах, render.py и JS (см. @source в
# static/src/app.css). Поэтому сюда копируется код, а не только CSS.
COPY app /vendor/web/app
COPY static /vendor/web/static
RUN mkdir -p /css \
 && npx @tailwindcss/cli -i web/static/src/app.css -o /css/app.css --minify

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=vendor /out /app/static/vendor
COPY . .
# После COPY . .: собранный app.css не лежит в репозитории и не должен
# перетираться ничем из контекста сборки.
COPY --from=vendor /css/app.css /app/static/app.css
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
