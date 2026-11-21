# はてなブックマーク特集の非公式RSS（GitHub Actions + GitHub Pages）

「テクノロジー」内の次の **3つの人気エントリーページそのもの** から、独立したRSS 2.0フィードを作ります。単なるキーワード検索とは異なります。

| 特集 | 取得元 | 生成するRSS |
|---|---|---|
| IT | https://b.hatena.ne.jp/hotentry/it/IT | `it.xml` |
| AI・機械学習 | https://b.hatena.ne.jp/hotentry/it/AI%E3%83%BB%E6%A9%9F%E6%A2%B0%E5%AD%A6%E7%BF%92 | `ai.xml` |
| プログラミング | https://b.hatena.ne.jp/hotentry/it/%E3%83%97%E3%83%AD%E3%82%B0%E3%83%A9%E3%83%9F%E3%83%B3%E3%82%B0 | `programming.xml` |

## 推奨セットアップ：GitHub Desktopを使う（Mac）

1. このZIPを展開します。出てきた `hatena-special-rss` フォルダを使います。
2. GitHub Desktopを開き、`File` → `Add Local Repository...` → `Choose...` でフォルダを選びます。
3. 「Gitリポジトリではない」と表示されたら `Create a Repository Here` を押します。ブランチ名は **`main`** にしてください。
4. `Commit to main` でコミットし、`Publish repository` でGitHubに公開します。**Public** にしてください（個人のGitHub無料プランのPagesで利用するため）。
5. GitHubのリポジトリの `Settings` → `Pages` → `Build and deployment` → `Source` を **GitHub Actions** にします。
6. リポジトリの `Actions` タブ → `Update Hatena special RSS` → `Run workflow` → 緑色の `Run workflow` を押して、実行結果を確認します。
7. `Settings` → `Pages` に掲載された公開URLを開いてください。3本のRSSのリンクが表示されます。
8. その3本をInoreaderで **URLからフィードを追加** します。

## 公開URLの例

GitHubユーザー名が `yourname`、リポジトリ名が `hatena-special-rss` なら：

- `https://yourname.github.io/hatena-special-rss/it.xml`
- `https://yourname.github.io/hatena-special-rss/ai.xml`
- `https://yourname.github.io/hatena-special-rss/programming.xml`
- 確認画面 `https://yourname.github.io/hatena-special-rss/`

※ URLは**例**です。初回のGitHub Pages公開が完了するまでアクセスできません。

## 仕組みと安全策

- GitHub Actionsの `17 */2 * * *`（UTC）で約2時間ごとに実行、または手動実行できます。定時実行は遅延・欠落することがあります。
- 3つの特集ページを個別に取得し、ページ中の `div.entrylist-contents` の記事カードからタイトル・記事URL・ブックマーク数などを抽出します。
- RSS各記事のGUIDはURLから生成するため、一覧の掲載順が変わってもInoreaderで重複しにくくなっています。
- 配信上の日時は「RSSで最初に検出した日時」を使い、元記事の古い公開日時で新着が埋もれにくいようにしています。履歴は`state.json`に120日分保持します。
- 取得エラー・HTML変更で記事が少なすぎる場合、前回取得できたRSSを維持し、サイト上に「取得失敗」と表示します。ただし初回から取得できない場合はエラー終了します。
- RSSと最初に検出した日時などはリポジトリに自動保存されます。これにより定期的にリポジトリの更新活動が発生しやすくなります。
- GitHubの「公開リポジトリで60日間活動がないと定期実行が自動無効化される」という制限は残ります。自動コミットが止まった状態が続いたときはActions画面を確認して再有効化してください。
- **はてな側の仕様変更、アクセス制限・通信障害、GitHub Actionsの遅延や停止による欠落が絶対にないとは保証できません。**

## トラブルシューティング

- **GitHub Pagesにページが出ない**: リポジトリの `Settings` → `Pages` の `Source` が `GitHub Actions` か確認。Actionsの実行が成功しているか確認。
- **`Permission denied` / `403` でgit push失敗**: `Settings` → `Actions` → `General` の `Workflow permissions` を確認し、許可される場合は `Read and write permissions` を選択。組織ポリシーにより制限される場合があります。
- **「取得した記事が3件未満」**: はてなのHTML構造変更、ブロック、ネットワーク障害の可能性があります。`generate.py`の `parse_entries()` を調整する必要があります。
- **一部のRSSが更新されない**: トップページを開くと前回成功日と取得の成否を確認できます。
- **定期更新が止まる**: Actionsの無効化・失敗と、60日間アクティビティ制限を確認します。

## テストと開発

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 generate.py
```

2026-11-21時点でページ構成をWeb閲覧で調査し、テスト用HTMLでRSS生成・XML整合性・GUID安定性を検証済みです。**こちらの実行環境でははてなブックマークへのプログラムによる通信ができないため、本番ページのHTMLを実際にスクレイピングする統合テストは未実施です。** 初回GitHub Actions実行で確認が必要です。

このツールは個人的な情報収集用の非公式実装です。はてなブックマークとの公式な提携や保証はありません。取得頻度は控えめにしてください。
