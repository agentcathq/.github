<div align="center">
  <img alt="AgentCat — see exactly how agents experience your product" src="docs/static/og-image.png" width="80%">
</div>
<h3 align="center">
    <a href="#why-use-agentcat-">Features</a>
    <span> · </span>
    <a href="https://agentcat.com">Website</a>
    <span> · </span>
    <a href="https://docs.agentcat.com">Docs</a>
    <span> · </span>
    <a href="#free-for-open-source">Open Source</a>
    <span> · </span>
    <a href="https://discord.gg/n9qpyhzp2u">Discord</a>
</h3>
<p align="center">
  <a href="https://badge.fury.io/py/agentcat"><img src="https://badge.fury.io/py/agentcat.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/agentcat/"><img src="https://img.shields.io/pypi/dm/agentcat.svg" alt="PyPI downloads"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://badge.fury.io/js/agentcat"><img src="https://badge.fury.io/js/agentcat.svg" alt="npm version"></a>
  <a href="https://www.npmjs.com/package/agentcat"><img src="https://img.shields.io/npm/dm/agentcat.svg" alt="npm downloads"></a>
</p>

> [!IMPORTANT]
> **MCPcat is now AgentCat** 🐱 — same team, same product, new name. The old `mcpcat` packages keep working forever, but new features land in `agentcat`.

AgentCat is an analytics platform for MCP server owners 🐱. It captures user intentions and behavior patterns to help you understand what AI users actually need from your tools — eliminating guesswork and accelerating product development all with one-line of code.

🎉 AgentCat now offers open source support for existing observability platforms, like [OpenTelemetry](https://opentelemetry.io/), [Datadog](https://www.datadoghq.com/), [Sentry](https://sentry.io/), and [PostHog](https://posthog.com/). Contribute or message us to add support for yours today 🎉

```bash
npm install agentcat
```
Checkout the [TypeScript SDK here](https://github.com/agentcathq/agentcat-typescript-sdk) — [setup guide](https://docs.agentcat.com/languages/typescript).

```bash
pip install agentcat
```
Checkout the [Python SDK here](https://github.com/agentcathq/agentcat-python-sdk) — [setup guide](https://docs.agentcat.com/languages/python).

```bash
# mark3labs/mcp-go
go get go.agentcat.com/sdk/mcpgo/v2

# official modelcontextprotocol/go-sdk
go get go.agentcat.com/sdk/officialsdk/v2
```
Checkout the [Go SDK here](https://github.com/agentcathq/agentcat-go-sdk), for [mcp-go](https://github.com/mark3labs/mcp-go) and the official [go-sdk](https://github.com/modelcontextprotocol/go-sdk) — [setup guide](https://docs.agentcat.com/languages/go).

```bash
composer require agentcat/sdk
```
Checkout the [PHP SDK here](https://github.com/agentcathq/agentcat-php-sdk) — [setup guide](https://docs.agentcat.com/languages/php).

```bash
dotnet add package AgentCat
```
Checkout the [C# SDK here](https://github.com/agentcathq/agentcat-csharp-sdk) — [setup guide](https://docs.agentcat.com/languages/csharp).

```bash
cargo add agentcat-sdk
```
Checkout the [Rust SDK here](https://github.com/agentcathq/agentcat-rust-sdk) — [setup guide](https://docs.agentcat.com/languages/rust).

```xml
<dependency>
    <groupId>com.agentcat</groupId>
    <artifactId>agentcat-java-sdk</artifactId>
    <version>1.0.0</version>
</dependency>
```
Checkout the [Java SDK here](https://github.com/agentcathq/agentcat-java-sdk) — [setup guide](https://docs.agentcat.com/languages/java).

```bash
bundle add agentcat
```
Checkout the [Ruby SDK here](https://github.com/agentcathq/agentcat-ruby-sdk) — [setup guide](https://docs.agentcat.com/languages/ruby).

Create an account for free today at [agentcat.com](https://agentcat.com).

## Why use AgentCat? 🤔

AgentCat helps developers and product owners build, improve, and monitor their MCP servers by capturing user analytics and tracing tool calls.

Use AgentCat for:

- **User session replay** 🎬. Follow alongside your users to understand why they're using your MCP servers, what functionality you're missing, and what clients they're coming from.
- **Trace debugging** 🔍. See where your users are getting stuck, track and find when LLMs get confused by your API, and debug sessions across all deployments of your MCP server.
- **Existing platform support** 📊. Get logging and tracing out of the box for your existing observability platforms (OpenTelemetry, Datadog, Sentry) — eliminating the tedious work of implementing telemetry yourself.

<img alt="AgentCat architecture — the AgentCat SDK inside your MCP server sends analytics to your observability vendors and session replay to the AgentCat dashboard" src="docs/static/architecture.png" />

## Supported MCP SDKs

| SDK | Version | Status |
|-----|---------|--------|
| 🟦 [TypeScript](https://github.com/agentcathq/agentcat-typescript-sdk) · [Docs](https://docs.agentcat.com/languages/typescript) | MCP TypeScript SDK v1.11+ and v2 | ✅ Available |
| 🐍 [Python](https://github.com/agentcathq/agentcat-python-sdk) · [Docs](https://docs.agentcat.com/languages/python) | MCP v1.2.0+ · FastMCP v3.0.0+ | ✅ Available |
| 🐹 [Go](https://github.com/agentcathq/agentcat-go-sdk) · [Docs](https://docs.agentcat.com/languages/go) | mcp-go v0.53.0+ · go-sdk v1.4.1+ | ✅ Available |
| 🐘 [PHP](https://github.com/agentcathq/agentcat-php-sdk) · [Docs](https://docs.agentcat.com/languages/php) | mcp/sdk 0.8.1+ · laravel/mcp 1.x · symfony/mcp-bundle 0.13+ | ✅ Available |
| 🟪 [C#](https://github.com/agentcathq/agentcat-csharp-sdk) · [Docs](https://docs.agentcat.com/languages/csharp) | ModelContextProtocol 1.0.0+ | ✅ Available |
| 🦀 [Rust](https://github.com/agentcathq/agentcat-rust-sdk) · [Docs](https://docs.agentcat.com/languages/rust) | rmcp 3.0.0+ | ✅ Available |
| ☕ [Java](https://github.com/agentcathq/agentcat-java-sdk) · [Docs](https://docs.agentcat.com/languages/java) | MCP Java SDK 2.0.1 · Spring Boot · Quarkus · Micronaut | ✅ Available |
| 💎 [Ruby](https://github.com/agentcathq/agentcat-ruby-sdk) · [Docs](https://docs.agentcat.com/languages/ruby) | mcp gem 0.23.0+ | ✅ Available |

## Supported Observability Platforms

  | Platform | Version | Status |
  |----------|---------|--------|
  | 📊 [OpenTelemetry](https://opentelemetry.io/) | v1.0.0+ | ✅ Available |
  | 🐕 [Datadog](https://www.datadoghq.com/) | v2.0.0+ | ✅ Available |
  | 🔍 [Sentry](https://sentry.io/) | v7.0.0+ | ✅ Available |
  | 🦔 [PostHog](https://posthog.com/) | - | ✅ Available (TypeScript, Go, PHP, C#, Ruby) |

The Rust and Java SDKs have no exporters yet.

Since AgentCat supports OpenTelemetry, check to see if your existing vendor or platform is already [supported](https://opentelemetry.io/ecosystem/vendors/)!

## Free for open source

AgentCat is free for qualified open source projects. We believe in supporting the ecosystem that makes MCP possible. If you maintain an open source MCP server, you can access our full analytics platform at no cost.

**How to apply**: Email hi@agentcat.com with your repository link

_Already using AgentCat? We'll upgrade your account immediately._

## Community Cats 🐱

Meet the cats behind AgentCat! Add your cat to our community by submitting a PR with your cat's photo in the `docs/cats/` directory.

<div align="left">
  <img src="docs/cats/bibi.png" alt="bibi" width="80" height="80">
  <img src="docs/cats/zelda.jpg" alt="zelda" width="80" height="80">
</div>

_Want to add your cat? Create a PR adding your cat's photo to `docs/cats/` and update this section!_
