# Arduino Work

Arduino CLIでスケッチの編集・ビルド・書き込み・シリアル通信をまとめる、ターミナルアプリです。オレンジ色の画面で、整備ロボットがマイコンへプログラムを注入します。

```sh
./bin/arduino-work --demo
```

デモは実機への書き込みを行いません。

## 必要なもの

- macOSまたはLinuxの端末（推奨100列×30行以上）
- [Arduino CLI](https://docs.arduino.cc/arduino-cli/installation/) と対象ボードのコア
- [uv](https://docs.astral.sh/uv/) とPython 3.11以上（uvが実行時に使用）
- Neovim 0.12以上（ビルド前の編集ファイルの保存に使用）

Pythonの追加パッケージや常駐サービスは不要です。

## 使い方

```sh
git clone https://github.com/meidon-jp/arduino-work.git
cd arduino-work
./bin/arduino-work --root ~/prog/mcu
```

`--root` はスケッチの検索先と設定の保存先です。省略すると `~/prog/mcu` を使います。起動後は矢印キーまたは `j` / `k` で選択し、Enterで実行します。Escまたは`q`で戻ります。

1. スケッチを選びます。新規作成やパスの直接入力もできます。
2. ボードと接続ポートを選び、通信速度を `Serial.begin(...)` に合わせます。
3. 「書き込み → シリアルモニタ」を選びます。ビルド成功後に書き込み、モニタを開きます。

ボード・ポート・通信速度はスケッチを切り替えても保持されます。作業ルートの `.arduino-work/state.json` に保存するので、公開リポジトリには追加しないでください。別の機器へ接続したらポートとボードを確認してください。

```sh
./bin/arduino-work --root ~/prog/mcu build    # ビルド
./bin/arduino-work --root ~/prog/mcu upload   # ビルドと書き込み
./bin/arduino-work --root ~/prog/mcu run      # 書き込み後モニタ
./bin/arduino-work --root ~/prog/mcu monitor  # モニタ
./bin/arduino-work --plain                    # 番号入力の画面
```

画面のビルド中はログを表示し、`q` / Esc / Ctrl+Cで中止できます。シリアル画面は受信時に表情が変わります。文字を入力してEnterで送信し、EscまたはCtrl+Cで終了します。モニタ中にCLIが表示する接続メッセージにも表情が反応します。

### Neovimの自動保存

ビルド前に、同じユーザー・同じ実行環境で起動したNeovimの標準RPCソケットを探し、対象スケッチ内の未保存ソースを保存します。対象外のファイルは保存しません。複数のNeovimで同じファイルが変更されている場合や保存に失敗した場合、ビルドを中止します。独自の `--listen`、異なる `XDG_RUNTIME_DIR`、別ホストのNeovimは検出されないため、手動で保存してください。保存後の編集は次回のビルドに反映されます。

### ボードとライブラリ

メニューからコアやライブラリを検索・導入できます。Arduino対応のコアが提供するボードとFQBNを利用でき、追加のボード設定も選べます。Picoの初回UF2コピー、独自プログラマ、Linuxのポート権限などは各ボードの手順を確認してください。Arduinoに対応していないマイコンは対象外です。

### 検証

```sh
uv run --no-project python -m unittest discover -s tests -v
```

Neovimのテストは一時フォルダで起動したプロセスを使用します。実機への書き込みとシリアルモニタの実機検証は環境に応じて行ってください。

## ライセンス

[MIT License](LICENSE)。表示用の文字絵は本プロジェクトのオリジナルです。
