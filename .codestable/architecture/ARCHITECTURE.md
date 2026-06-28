# Crossroads Agent Café 架构总入口

> 状态：骨架（待填充）
> 创建日期：2026-06-19

## 1. 项目简介

Crossroads Agent Café 是一个 FastAPI 应用，包含静态 HTML/CSS/JS 前端、SQLAlchemy ORM、MySQL 持久化、Redis 短期记忆、A2A Skill/EvoMap 点单集成，以及 WebSocket 可视化事件流。

## 2. 核心概念 / 术语表

## 3. 子系统 / 模块索引

## 4. 关键架构决定

## 5. 已知约束 / 硬边界

- MySQL 是唯一支持的关系型数据库。
- Redis 是唯一支持的记忆/中间件后端。
- Web dialog 点单路径与 A2A Skill/EvoMap 点单路径共享订单与事件持久化，但支付逻辑保持分离，除非另有明确架构决定。
