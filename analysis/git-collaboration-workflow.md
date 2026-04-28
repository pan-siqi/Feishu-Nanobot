# Git 多人协作完整流程（团队版）

> 目标：把「从拉代码到 PR 合并、再到下一轮开发」写成可照抄的检查清单。  
> 约定：下文默认主分支名为 **`master`**；若团队使用 **`main`**，将所有 `master` 替换为 `main` 即可。

---

## 1. 名词与对象（先对齐语言）

| 概念 | 含义 |
|------|------|
| **远程（remote）** | 托管在 GitHub / GitLab 等上的仓库副本，本机里通常叫 `origin`。 |
| **`origin/master`** | 远程上 `master` 分支当前指向的提交（本地通过 `fetch` 更新认知，不自动改你工作区）。 |
| **功能分支（feature branch）** | 从主分支拉出、只承载某一功能或修复的分支，例如 `feature/mxwang-login`。 |
| **PR / MR** | Pull Request / Merge Request：在网页上请求「把某功能分支合并进主分支」，供评审与 CI。 |
| **fast-forward / non-fast-forward** | 推送时若远程已有你本地没有的提交，直接 `push` 可能被拒绝，需要先拉取并合并或变基。 |

---

## 2. 分支策略（推荐最小集）

- **`master`**：始终可发布或可集成的基线；**禁止**长期直接在 `master` 上堆业务开发（紧急热修可单独约定）。  
- **`feature/<作者或简述>/<任务>`**：一人或一任务一分支，生命周期从「开任务」到「PR 合并」为止。  
- **可选 `develop`**：若团队采用 Git Flow，日常集成在 `develop`，发布前再合并到 `master`；若无此约定，可忽略。

---

## 3. 一次性环境配置（每台新机器做一次）

### 3.1 身份（避免提交显示为 `user@hostname`）

```bash
git config --global user.name "你的显示名"
git config --global user.email "你在 Git 平台绑定的邮箱"
```

邮箱建议与 GitHub 账号一致，或使用平台提供的 `noreply` 地址。

### 3.2 默认分支与远程

克隆后确认：

```bash
git remote -v
git branch -vv
```

确认 `origin` 指向正确仓库，且本地 `master` 跟踪 `origin/master`（或按团队文档配置）。

### 3.3 可选：默认推送行为（Git 2.37+）

```bash
git config --global push.autoSetupRemote true
```

首次推送新分支时可少记一次 `-u`（仍建议团队统一文档写明习惯）。

---

## 4. 完整协作循环（可重复的标准流程）

### 阶段 A：开工 —— 从最新主分支开功能分支

```bash
git fetch origin
git checkout master
git pull origin master
git checkout -b feature/<你的名字或缩写>-<简短任务描述>
```

**检查**：`git status` 应为干净（无意外未提交文件），或你明确知道哪些改动要带进本分支。

---

### 阶段 B：开发 —— 小步提交

```bash
# 编辑代码后
git add -p          # 可选：按块审查再暂存；或直接 git add <路径>
git commit -m "动词开头的一句话说明，例如：Add feishu webhook handler"
```

**习惯**：一条 commit 做一件可理解的事；大改动可拆多次提交，便于评审与回滚。

---

### 阶段 C：同步主分支 —— 推送前减少冲突

主分支会不断合并别人的 PR，你的功能分支会「落后」。推送前或 PR 前建议做一次：

**方式一：合并（默认推荐，安全、不改已推送历史）**

```bash
git fetch origin
git merge origin/master
# 若有冲突：编辑文件 → git add <文件> → git commit（完成 merge）
```

**方式二：变基（历史更直，需团队允许；已 push 的分支可能要强推）**

```bash
git fetch origin
git rebase origin/master
# 若有冲突：改文件 → git add → git rebase --continue
# 若该分支曾 push 过：git push --force-with-lease
```

**merge 与 rebase 怎么选**：见本文 **第 7 节**。

---

### 阶段 D：推送到远程

**该分支第一次推送：**

```bash
git push -u origin feature/<你的分支名>
```

**之后在同一分支上：**

```bash
git push
```

---

### 阶段 E：评审 —— 开 PR / MR

1. 在 GitHub（或团队平台）选择 **base = `master`**，**compare = 你的功能分支**。  
2. 写清标题与说明（动机、改动范围、如何验证）。  
3. 指定评审人（如管理者）；按评论继续在同一分支上 `commit` + `push`，PR 会自动更新。

---

### 阶段 F：合并之后 —— 本地与远程清理

```bash
git fetch origin
git checkout master
git pull origin master
```

**删除已合并的本地功能分支（可选）：**

```bash
git branch -d feature/<你的分支名>
```

**删除远程功能分支（若平台未自动删）：**

```bash
git push origin --delete feature/<你的分支名>
```

**下一任务**：从最新 `master` 再执行 **阶段 A**，新建新的 `feature/...`。

---

## 5. 与「管理者合并」配合时的注意点

- **不要 force push 到共享分支**（如 `master`、`develop`）；仅在你自己的 `feature/*` 上、且团队允许时，对「已推送需 rebase 整理」的情况使用 `git push --force-with-lease`。  
- **PR 尽量小、可审**：大需求可拆多个 PR 或按模块提交。  
- **CI 失败**：优先在本地复现并修复，再 push；避免依赖「合并后再修」。  
- **敏感信息**：密钥、Token 不进仓库；用环境变量或平台 Secret。

---

## 6. 常见问题与处理

### 6.1 `git push` 被拒绝（non-fast-forward）

含义：远程上该分支有你本地没有的提交。

```bash
git fetch origin
git merge origin/feature/<分支名>   # 或 rebase，视团队规范
# 解决冲突后
git push
```

若你确定远程该分支应被你的历史覆盖（慎用）：`git push --force-with-lease`。

### 6.2 误提交到错误分支

若尚未 push：可用 `git cherry-pick` 把提交挪到正确分支，或在正确分支上重做。  
若已 push：与管理者沟通，避免强行覆盖他人依赖的分支。

### 6.3 想改最后一次提交说明或漏 add 的文件

**尚未 push：**

```bash
git add <漏的文件>
git commit --amend --no-edit
```

**已 push**：amend 后需 `git push --force-with-lease`（仅限个人 feature 分支且团队同意）。

### 6.4 临时切换任务：保存当前工作

```bash
git stash push -m "wip: 简述"
git checkout 其他分支
# 回来继续
git checkout feature/xxx
git stash pop
```

---

## 7. Merge 与 Rebase 对照（决策用）

| 维度 | **merge** | **rebase** |
|------|-----------|------------|
| 历史形状 | 保留分叉，常有 merge commit | 更接近一条直线 |
| 提交哈希 | 不改写已有提交 | 变基范围内提交会换新哈希 |
| 已 push 的 feature 分支 | 通常直接 `git push` | 常需 `--force-with-lease` |
| 协作风险 | 低 | 需约定，避免他人基于旧提交开发 |

**建议**：向主分支「看齐」时用 **merge** 最省心；仅在个人未推送或团队明确允许时，用 **rebase** 整理历史。

---

## 8. 一页纸检查清单（打印或收藏）

- [ ] `user.name` / `user.email` 已配置  
- [ ] 开工：`fetch` → `checkout master` → `pull` → `checkout -b feature/...`  
- [ ] 开发：小步 `commit`，信息可读  
- [ ] 推送前：`fetch` + `merge origin/master`（或团队规定的 rebase 流程）  
- [ ] `git push -u origin feature/...`（首推）  
- [ ] 开 PR：base = `master`，说明清楚，@ 评审人  
- [ ] 合并后：本地 `pull` 最新 `master`，删除旧 feature 分支（可选）  
- [ ] 下一任务：从最新 `master` 再开新分支  

---

## 9. 与本仓库的对应关系

本仓库远程默认跟踪 **`origin/master`**（以你执行 `git symbolic-ref refs/remotes/origin/HEAD` 或 `git branch -r` 时为准）。协作流程以团队实际默认分支名为准，本文仅提供可替换的模板。

---

*文档版本：与团队分支命名、是否使用 `develop`、是否允许 rebase 强推等策略对齐后，可在本节追加「团队特例」一节。*
