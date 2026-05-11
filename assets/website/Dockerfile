FROM node:22-alpine

WORKDIR /app

COPY package.json server.mjs ./
COPY static ./static

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=8787
ENV GPM_REPO=/data/project-hub

EXPOSE 8787

CMD ["node", "server.mjs"]
