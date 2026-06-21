# 每日重要新闻邮件

每天从公开 RSS/Atom 新闻源抓取内容，按时效性、重大事件关键词和多源报道情况排序，然后通过 SMTP 发送一封 HTML 邮件。整个项目只使用 Python 标准库，不需要付费 API。

默认设置：

- 每天 `07:15`（`Asia/Tokyo`）运行
- 汇总最近 36 小时的新闻
- 发送评分最高的 12 条
- 支持中文、日文和英文新闻源
- 支持 GitHub Actions 页面手动运行和“只预览、不发送”

## 一、部署到 GitHub

1. 新建一个 GitHub 仓库，把本项目中的文件提交并推送到默认分支。
2. 打开仓库的 **Settings → Secrets and variables → Actions**。
3. 在 **Secrets** 中添加：

| 名称 | 内容 |
| --- | --- |
| `SMTP_USERNAME` | 发件邮箱，例如 `name@gmail.com` |
| `SMTP_PASSWORD` | Gmail 的 16 位应用专用密码，不是登录密码 |
| `EMAIL_TO` | 私人收件邮箱；多个地址用逗号分隔 |
| `EMAIL_FROM` | 可选；通常留空，程序会使用 `SMTP_USERNAME` |

如果使用 Gmail，需要先为 Google 账号开启两步验证，再创建“应用专用密码”。

4. 打开仓库的 **Actions → 每日重要新闻（自动 / 手动）→ Run workflow**。
5. 在 `operation` 中选择：
   - `send`：立即抓取新闻并发送邮件。
   - `preview`：不发送邮件，只生成 HTML 和纯文本预览。
6. 还可以为这次手动运行选择新闻条数、回溯时长和邮件标题前缀，然后点击绿色的 **Run workflow**。

选择 `preview` 后，可在本次运行页面底部的 **Artifacts → email-preview** 下载邮件预览。预览文件保留 3 天。

### 手动立即发送

进入 Actions 页面后：

1. 选择左侧的 **每日重要新闻（自动 / 手动）**。
2. 点击右侧的 **Run workflow**。
3. 将 `operation` 设为 `send`。
4. 根据需要选择 `6`、`12` 或 `20` 条新闻。
5. 点击绿色的 **Run workflow**。

任务运行成功后，邮件会立即发送到 Secret `EMAIL_TO` 配置的私人邮箱。手动运行不会改变每天 07:15 的自动发送计划。

> GitHub 的定时工作流只在默认分支运行。仓库长期没有活动时，GitHub 也可能暂停公开仓库的定时工作流。

## 二、调整发送时间

编辑 [`.github/workflows/daily-news.yml`](.github/workflows/daily-news.yml)：

```yaml
schedule:
  - cron: "15 7 * * *"
    timezone: "Asia/Tokyo"
```

`15 7 * * *` 表示每天 07:15。建议避开整点，因为 GitHub Actions 在整点附近更容易排队延迟。

例子：

- 每天 08:30：`30 8 * * *`
- 每周一至周五 07:00：`0 7 * * 1-5`
- 每天 18:45：`45 18 * * *`

## 三、自定义新闻

编辑 [`config/news_sources.json`](config/news_sources.json) 即可添加、关闭或调整新闻源：

```json
{
  "name": "某新闻源",
  "url": "https://example.com/rss.xml",
  "category": "财经",
  "language": "zh-CN",
  "weight": 1.5,
  "enabled": true
}
```

`weight` 越高，该来源的新闻越容易进入邮件。程序会跳过失效的单个新闻源，只要还有其他来源可用就会继续发送。

也可以在 GitHub Actions 的 **Variables** 中添加以下可选设置，无需改代码：

| 名称 | 默认值 | 说明 |
| --- | --- | --- |
| `NEWS_MAX_ITEMS` | `12` | 每封邮件的新闻条数 |
| `NEWS_LOOKBACK_HOURS` | `36` | 抓取多少小时内的内容 |
| `NEWS_MAX_SELECTED_PER_SOURCE` | `3` | 单一新闻源最多入选多少条 |
| `NEWS_MAX_SELECTED_PER_CATEGORY` | `4` | 单一类别优先最多入选多少条 |
| `NEWS_TIMEZONE` | `Asia/Tokyo` | 邮件中的时间显示时区 |
| `EMAIL_FROM_NAME` | `每日重要新闻` | 发件人显示名称 |
| `EMAIL_SUBJECT_PREFIX` | `每日重要新闻` | 邮件标题前缀 |

## 四、使用其他邮箱服务

在 Actions 的 **Variables** 中设置：

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_SECURITY`：`ssl`、`starttls` 或 `plain`

用户名和密码仍放在 **Secrets** 中。请以邮箱服务商当前提供的 SMTP 参数为准。

## 五、本地演练

需要 Python 3.11 或更新版本：

```bash
DRY_RUN=true python src/daily_news.py
```

演练不会发送邮件，会生成：

- `output/preview.html`
- `output/preview.txt`

运行测试：

```bash
python -m unittest discover -s tests -v
```

## 费用

代码本身没有付费依赖。GitHub Actions 对公开仓库的标准托管运行器免费；私人仓库每月包含一定免费额度。这个任务每天只运行一次，通常只占用很少的 Actions 时间。
