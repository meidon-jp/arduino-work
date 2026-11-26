# Arduino Work

Arduino CLIをターミナルから使いやすくするツールです．スケッチの選択からビルド，書き込み，シリアルモニタまでをメニューから操作できます．

ビルド中は整備ロボットが作業し，書き込み中はマイコンにデータを注入します．実機を接続せずに演出を試す場合は，次のコマンドを実行してください．

```sh
./bin/arduino-work --demo
```

## 必要なもの

- macOSまたはLinuxの端末（推奨100列×30行以上）
- [Arduino CLI](https://docs.arduino.cc/arduino-cli/installation/) と対象ボードのコア
- [uv](https://docs.astral.sh/uv/) とPython 3.11以上
- Neovim 0.12以上（ビルド前の編集ファイルの保存に使用）

Pythonの追加パッケージや常駐サービスは不要です．

## 使い方

1. リポジトリを取得し，Arduino Workを起動します．

   ```sh
   git clone https://github.com/meidon-jp/arduino-work.git
   cd arduino-work
   ./bin/arduino-work --root ~/prog/mcu
   ```

2. 「スケッチを選択」から書き込むプログラムを選びます．新規作成やパスの直接入力もできます．
3. ボードとポートを選び，通信速度をスケッチの `Serial.begin(...)` に合わせます．
4. 「書き込み → シリアルモニタ」を選ぶと，ビルドと書き込みの後にシリアルモニタが開きます．

メニューは矢印キーまたは `j` / `k` で選択し，Enterで実行します．Escまたは `q` で戻ります．処理中の `q` / Esc / Ctrl+Cで実行を中止できます．シリアルモニタでは，文字を入力してEnterで送信し，EscまたはCtrl+Cで終了します．

`--root` にはスケッチの検索先と設定の保存先を指定します．省略した場合は `~/prog/mcu` を使います．ボード・ポート・通信速度はスケッチを切り替えても保持します．設定は作業ルートの `.arduino-work/state.json` に保存するため，Gitへ追加しないでください．

設定後は，メニューを開かずに次のコマンドでも操作できます．

```sh
./bin/arduino-work --root ~/prog/mcu build    # ビルド
./bin/arduino-work --root ~/prog/mcu upload   # ビルドと書き込み
./bin/arduino-work --root ~/prog/mcu run      # 書き込み後にモニタ
./bin/arduino-work --root ~/prog/mcu monitor  # モニタ
./bin/arduino-work --plain                    # 番号入力の画面
```

## 機能

- スケッチの検索・作成，ボード・ポート・通信速度の選択
- ビルド，書き込み，シリアルモニタ，コア・ライブラリの検索と導入
- ビルド・書き込み中のアニメーションとログ表示
- シリアル受信時の表情の変化
- ビルド前のNeovimの未保存ファイルの保存

ビルド前は，同じユーザー・同じ実行環境で起動したNeovimの標準RPCソケットを探し，対象スケッチ内の未保存ソースを保存します．複数のNeovimで同じファイルが変更されている場合や，保存に失敗した場合はビルドを中止します．独自の `--listen`，異なる `XDG_RUNTIME_DIR`，別ホストのNeovimは検出できないため，手動で保存してください．保存後の編集は次回のビルドに反映されます．

## 検証

```sh
uv run --no-project python -m unittest discover -s tests -v
```

Neovimのテストは一時フォルダで起動したプロセスを使用します．実機への書き込みとシリアル通信は，使用するボードでも確認してください．

## 注意事項

- Arduino用のコアが提供されているボードを対象としています．Arduinoに対応していないマイコンは対象外です．
- ボードや接続機器を変更した場合は，ボード・ポート・通信速度を確認してください．
- Picoの初回UF2コピー，独自プログラマ，Linuxのポート権限などは，各ボードの手順を確認してください．
- シリアルモニタでは，Arduino CLIの接続メッセージにも表情が反応します．
- 生成AIによって生成されたソースコードを含みます．

## ライセンス

[MITライセンス](LICENSE)で公開しています．表示用の文字絵は本プロジェクトのオリジナルです．
