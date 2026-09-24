# CI/CD 流水线

简体中文 | 本文说明本仓库的三条 GitHub Actions 流水线、所需密钥与发版操作。

## 1. 架构速览（流水线据此编排）

| 层 | 位置 | 技术 | 构建 / 测试入口 |
| --- | --- | --- | --- |
| CS:GO Demo 抽取器 | `tools/csgo-demo-extract` | Go | `go vet` / `go test` / `go build`（复合 action `.github/actions/build-csgo-extractor`） |
| Python 后端 | `backend/` | Python 3.12 + FastAPI | `uv sync --frozen` + `pytest backend/tests` |
| React 前端 | `frontend/` | React 19 + Vite 6 + pnpm 11 | `pnpm test`（Vitest）+ `pnpm run build` |
| Tauri 桌面壳 | `frontend/src-tauri` | Rust + Tauri 2 | `cargo fmt/clippy/test` |
| Demo 饰品重写工具 | `tools/demo-cosmetic-rewriter` | Rust | `cargo fmt/clippy/test` |
| 更新代理 | `infra/cloudflare` | Cloudflare Worker | `wrangler deploy` |

依赖边界刻意分离：Python 用根目录 `uv.lock`，前端用 `frontend/pnpm-lock.yaml`，Rust 用各自 `Cargo.lock`。CI 一律用 `--frozen` / `--frozen-lockfile` / `--locked`，避免"锁文件没提交就悄悄升级"。

平台约束：录制、OBS、CS:GO 控制台注入只能在 Windows 上完整验证，因此**后端与前端测试跑在 `windows-latest`**；纯 Rust 工具链任务跑 `ubuntu-latest` 省时间。

## 2. 三条流水线

```
PR / push(main, develop)   ──▶ CI           构建 + 测试（不产出安装包）
tag v*.*.* / 手动触发      ──▶ Release      测试 → 签名 → NSIS → GitHub Release
                                            └─▶ Deploy  安装包 + latest.json/latest.yml → Cloudflare R2
push main (infra/cloudflare/**) ──▶ Worker  更新代理 Worker 部署
```

### `ci.yml` — 构建与测试

| Job | Runner | 内容 |
| --- | --- | --- |
| `extractor` | windows | gofmt / vet / test / build，产物 `csgo-demo-extract.exe` |
| `backend` | windows | `uv sync --frozen` → `app.demoparser_runtime` 校验 → `pytest backend/tests` |
| `frontend` | windows | i18n 校验 → Vitest → `vite build` → 上传 `frontend/dist` 产物 |
| `rust` | windows | Tauri 壳 fmt / clippy / test |
| `rust-tools` | ubuntu | `demo-cosmetic-rewriter` fmt / clippy / test |
| `ci-gate` | ubuntu | 汇总门：任一上游失败即红，**分支保护只需勾这一个 check** |

`paths-ignore` 排除 `*.md` / `docs/**` / `asset/**`；PR 之间自动取消旧运行，`main`/`develop` 不取消，保证每次提交都有完整记录。

### `release-windows.yml` — 构建、签名、发布、部署

`release` job（windows）：版本解析 → 依赖安装 → 后端 / 前端 / Rust 全量测试 → 导入代码签名证书 → `pnpm run desktop:build:ver` → 内置 Python runtime 校验 → 体积预算校验（安装包 ≤ 45 MiB，安装后 ≤ 120 MiB）→ SHA256SUMS → 上传产物 → GitHub Release。

`deploy` job（ubuntu）：下载上一步产物 → `pnpm run deploy:r2` 推送安装包与 updater 清单 → 轮询校验 `latest.json` 已生效。

手动触发时可指定 `version`、`update_mode`（`normal` / `force`）、`deploy`（是否推送 R2）。

### `deploy-cloudflare-worker.yml` — 更新代理

仅当 `infra/cloudflare/**` 变化时触发，用 Wrangler 部署 `update-proxy-worker.js`（合并 Range 请求，规避 Worker 50 子请求上限）。

## 3. 需要配置的 Secrets / Variables

在仓库 **Settings → Secrets and variables → Actions** 中配置。

| 名称 | 类型 | 用途 | 缺失时行为 |
| --- | --- | --- | --- |
| `TAURI_SIGNING_PRIVATE_KEY` | secret | updater 签名私钥（**构建阶段就要用，与 R2 无关**） | `createUpdaterArtifacts: true` 时**构建直接失败** |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | secret | 私钥口令（密钥有口令时必填） | 同上 |
| `WINDOWS_PFX_BASE64` | secret | 代码签名证书（Base64 PFX） | 产出未签名安装包 |
| `WINDOWS_PFX_PASSWORD` | secret | PFX 口令 | 配了 PFX 就必须配 |
| `R2_ENDPOINT` | secret | Cloudflare R2 S3 endpoint | deploy 跳过并告警 |
| `R2_ACCESS_KEY_ID` | secret | R2 访问密钥 | deploy 跳过并告警 |
| `R2_SECRET_ACCESS_KEY` | secret | R2 私钥 | deploy 跳过并告警 |
| `CLOUDFLARE_API_TOKEN` | secret | Worker 部署令牌 | Worker 部署跳过并告警 |
| `CLOUDFLARE_ACCOUNT_ID` | secret | Cloudflare 账户 ID | 同上 |
| `R2_BUCKET` | variable | 默认 `cs-demo-agent` | — |
| `R2_PUBLIC_BASE_URL` | variable | 默认 `https://pub-7920152f7eff45c19b5a1750e55acd42.r2.dev` | — |

`production` environment 会在首次运行时自动创建；建议在 Settings → Environments 里给它加上 reviewers，避免误推更新通道。

### 不要 Cloudflare R2 完全可以

R2 只是**更新分发通道**，不是构建依赖。三个 R2 secret 都没配时，`deploy` job 会打一条 warning 然后跳过，构建、签名、GitHub Release 全部照常，流水线依然是绿的——用户照旧从 Releases 页面手动下载安装包。

但注意区分两件事：

- **不配 R2** → 没问题，只影响客户端自动更新。
- **不配 `TAURI_SIGNING_PRIVATE_KEY`** → 有问题，而且问题出在**构建阶段**。`tauri.conf.json` 里 `plugins.updater.pubkey` 已填且 `bundle.createUpdaterArtifacts: true`，Tauri 会硬报错：

  ```
  A public key has been found, but no private key.
  Make sure to set TAURI_SIGNING_PRIVATE_KEY environment variable.
  ```

  所以要么配上这个 secret，要么彻底关掉自动更新：把 `bundle.createUpdaterArtifacts` 改为 `false`，并删掉 `plugins.updater` 整段。Cargo 侧的 `tauri-plugin-updater` 与 `src-tauri/src/lib.rs` 里的注册不必动，删配置不会导致编译失败；前端 `shouldCheckAppUpdates()` 只会跳过更新检查（`endpoints` 本来就是空数组）。

  工作流里已加了一步 `Verify updater signing configuration`，会在 20 分钟的打包开始前就明确报出这个原因，而不是让你对着 Tauri 的英文错误猜。

## 4. 分支保护

Settings → Branches → `main` / `develop`：

- Require a pull request before merging
- Require status checks to pass → 勾选 **`CI gate`**
- Require branches to be up to date before merging

## 5. 发版步骤

```bash
git checkout develop && git pull
# 版本号对齐：frontend/package.json、frontend/src-tauri/Cargo.toml、tauri.conf.json、pyproject.toml
git checkout main && git merge develop
git tag v2.6.0 && git push origin main --tags
```

推送 tag 后 `Release Windows` 自动跑完构建、GitHub Release 和 R2 部署。想重跑或强制更新：

Actions → Release Windows → Run workflow → 填 `version`，按需设 `update_mode=force`。

## 6. 本地等价命令

```bash
# 后端
uv sync --frozen && uv run --frozen python -m pytest backend/tests -q

# 前端
cd frontend && pnpm install --frozen-lockfile && pnpm run check:i18n && pnpm test && pnpm run build

# Rust
cd frontend/src-tauri && cargo fmt --check && cargo clippy --all-targets --locked -- -D warnings && cargo test --locked
cd ../../tools/demo-cosmetic-rewriter && cargo fmt --check && cargo clippy --all-targets --locked -- -D warnings && cargo test --locked
```

## 7. 常见故障

| 现象 | 原因 / 处理 |
| --- | --- |
| `demoparser_runtime` 校验失败 | 定制 wheel 版本不匹配或缺失 Rust 接口，检查 `uv.lock` 与 `packaging/demoparser-lean/demoparser-runtime.json` |
| `Installer exceeds 45 MiB budget` | `bundle-resources` 体积膨胀，先看 `dist/runtime-size-report.json` |
| R2 部署报 `Updater signature not found` | 构建时未设置 `TAURI_SIGNING_PRIVATE_KEY(_PASSWORD)` |
| `Authenticode validation failed` | PFX 导入成功但签名未生效，确认证书含私钥且未过期 |
| Rust job 报 `-D warnings` | 本地跑一遍 `cargo clippy --all-targets` 即可复现 |
