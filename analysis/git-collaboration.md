# Git 多人协作完整流程（团队版总结）

> 适用场景：基于 GitHub / GitLab / Gitee 等平台，通过 **功能分支 + Pull Request / Merge Request** 由管理者或 Code Owner 合并进主分支。  
> 本文档约定：远程名为 `origin`，主分支名为 **`master`**（若团队使用 `main`，将文中 `master` 全部替换为 `main` 即可）。

---

## 1. 核心概念（读一遍就够日常用）

| 概念 | 含义 |
|------|------|
| **远程（remote）** | 托管在服务器上的仓库副本，通常叫 `origin`，对应你 `git clone` 的地址。 |
| **主分支** | 线上「稳定基准」，本仓库为 `master`。不在此分支上堆长期未评审的改动。 |
| **功能分支** | 每人每个任务一条线，例如 `feature/mxwang-xxx`、`fix/issue-42`。 |
| **fetch** | 只拉远程**信息**（提交、分支指针），默认不改你当前工作区文件。 |
| **pull** | 在**当前分支**上，相当于 `fetch` + 把远程对应分支**合并进当前分支**。 |
| **push** | 把本地提交上传到远程；首次推新分支常用 `git push -u origin <分支名>`。 |
| **PR / MR** | Pull Request / Merge Request：请求把某功能分支**合并进主分支**，走评审与 CI。 |

---

## 2. 一次性环境配置（每台电脑做一次）

```bash
git config --global user.name "你的显示名"
git config --global user.email "你在 Git 平台绑定的邮箱"
```

可选（减少 HTTPS 重复输入，按平台文档配置 credential 或改用 SSH）。

查看远程与默认分支：

```bash
git remote -v
git symbolic-ref refs/remotes/origin/HEAD
```

---

## 3. 标准协作循环（可反复执行的一条龙）

把下面 **A → H** 当作「一个功能从开工到收尾」的模板；下一个功能重复即可。

### A. 开工前：主分支对齐远程

```bash
git fetch origin
git checkout master
git pull origin master
```

确保本地 `master` 与 `origin/master` 一致，减少从过时基点开分支。

### B. 从最新主分支创建功能分支

```bash
git checkout -b feature/你的名字-简短说明
```

命名建议：`feature/`、`fix/`、`docs/` 等前缀 + 可识别片段，避免所有人叫 `test`。

### C. 开发与提交

```bash
# 改代码后
git status
git add <文件>          # 或 git add .（注意别误加密钥）
git commit -m "简明说明本次改动"
```

习惯：小步提交、信息可读；无关改动不要混在同一提交里（便于回滚与评审）。

### D. 推送远程（首次与之后）

**第一次**从本机推该分支：

```bash
git push -u origin feature/你的名字-简短说明
```

`-u`（`--set-upstream`）绑定本地分支与 `origin` 上同名分支，之后在同一分支上：

```bash
git push
```

### E. 发起合并请求（PR / MR）

在网页上：**base** 选 `master`，**compare** 选你的功能分支，写清楚动机、风险、测试方式，@ 评审人。

### F. 评审期间：同一分支继续改

```bash
git add ...
git commit -m "..."
git push
```

PR 会自动更新；无需新开 PR（除非团队规定拆 PR）。

### G. 主分支有更新时：把 `master` 同步进功能分支（推送 PR 前尤其要做）

任选一种策略（团队应统一；不确定时优先 **merge**）。

**方式一：merge（最安全、最省事）**

```bash
git fetch origin
git checkout feature/你的名字-简短说明
git merge origin/master
# 若有冲突：编辑文件 → git add → git commit
git push
```

**方式二：rebase（历史更直，已 push 的分支慎用）**

```bash
git fetch origin
git checkout feature/你的名字-简短说明
git rebase origin/master
# 若有冲突：解决 → git add → git rebase --continue
# 若该分支曾 push 过，更新远程一般为：
git push --force-with-lease
```

`--force-with-lease` 比 `--force` 更安全：若远程有别人新推的提交会拒绝覆盖。

### H. PR 合并之后：本地收尾

```bash
git fetch origin
git checkout master
git pull origin master
```

可选清理：

```bash
git branch -d feature/你的名字-简短说明    # 删除本地已合并分支
# 远程分支若平台未自动删：
git push origin --delete feature/你的名字-简短说明
```

下一个功能从 **A** 重新开始。

---

## 4. Merge 与 Rebase：区别与选用

| | **merge** | **rebase** |
|---|-----------|------------|
| 历史 | 保留分叉，常有 merge commit | 常呈一条线，少 merge 节点 |
| 提交哈希 | 不改变已有提交 | 变基范围内提交会重写 |
| 已 push 的分支 | 通常直接 `git push` | 常需 `git push --force-with-lease` |
| 建议场景 | 默认选择；多人协作、公共分支 | 仅个人分支、未推送或团队允许整理历史 |

**原则**：不要对多人已基于其工作的分支随意 rebase + 强推；主分支保护策略以团队规范为准。

---

## 5. 冲突（conflict）处理要点

出现冲突时 Git 会在文件里标 `<<<<<<<`、`=======`、`>>>>>>>`。

1. 人工编辑保留正确内容，删掉标记行。  
2. `git add` 已解决文件。  
3. **merge 未结束**：直接 `git commit`。  
4. **rebase 未结束**：`git rebase --continue`（放弃则 `git rebase --abort`）。

---

## 6. 常见问题速查

| 现象 | 处理思路 |
|------|----------|
| `rejected` / `non-fast-forward` | 先 `git fetch`，再对功能分支 `merge origin/master` 或 `rebase origin/master`，解决冲突后 `git push`（rebase 后可能需 `--force-with-lease`）。 |
| 提交后发现作者显示成 `user@hostname` | 配置 `user.name` / `user.email`；仅改最后一次提交作者：`git commit --amend --reset-author`（已 push 需团队同意再强推）。 |
| 误提交大文件或密钥 | 立即联系管理者；可能需 `git filter-repo` 等历史清理，并轮换密钥。 |
| 想撤销工作区未 add 的改动 | `git checkout -- <文件>` 或 `git restore <文件>`（Git 2.23+）。 |
| 想撤销已 add 未 commit | `git restore --staged <文件>`。 |

---

## 7. 团队协作规范建议（可贴进 CONTRIBUTING）

1. **禁止直接在 `master` 上堆未评审提交**（若仓库未开分支保护，也应自觉遵守）。  
2. **一个 PR 尽量单一主题**，大改动可拆多个 PR。  
3. **合并前**功能分支应包含最新 `origin/master`（见 3-G）。  
4. **提交信息**能独立看懂「做了什么、为什么」；避免无意义 message。  
5. **已合并分支**及时删除，避免远程分支堆积。  
6. **强推**仅限个人功能分支且团队知情；禁止对 `master` 强推改写公共历史。

---

## 8. 一页纸检查清单（打印或收藏）

- [ ] `user.name` / `user.email` 已配置  
- [ ] 开工：`fetch` → `checkout master` → `pull`  
- [ ] `checkout -b feature/...`  
- [ ] 开发 → `add` → `commit`  
- [ ] 推 PR 前：`merge origin/master`（或团队约定的 rebase）  
- [ ] `push`（首次 `-u`）  
- [ ] 网页开 PR，base = `master`  
- [ ] 合并后：本地 `pull` 更新 `master`，删旧功能分支  

---

## 9. 与本文档相关的仓库事实（便于对齐）

本仓库远程默认跟踪分支曾为 **`origin/master`**（以你执行 `git symbolic-ref refs/remotes/origin/HEAD` 的当前结果为准）。若组织迁移到 `main`，请同步更新 CI、分支保护与本文档中的分支名。

---

*文档版本：与仓库协作方式同步维护；流程以团队最终规范为准。*
