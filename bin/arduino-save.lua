-- 一時的なRPCクライアント。設定・プラグイン・ShaDaを読み書きしない。
-- argv[2]以降はテストや独自 --listen ソケットの明示指定用。
local uv = vim.uv
local root = assert(uv.fs_realpath(arg[1]), "スケッチが見つかりません")
local channels = {}
local remote = [[
local root, expected = ...
local uv = vim.uv
local extensions = { ino=true, pde=true, c=true, cpp=true, cc=true, cxx=true,
                     h=true, hh=true, hpp=true, hxx=true, s=true, S=true }
local function path_for(buf)
  local name = vim.api.nvim_buf_get_name(buf)
  if name == '' then return nil end
  local path = uv.fs_realpath(name)
  if not path then
    local parent = uv.fs_realpath(vim.fs.dirname(name))
    if parent then path = parent .. '/' .. vim.fs.basename(name) end
  end
  if path and path:sub(1, #root + 1) == root .. '/'
      and extensions[path:match('%.([^./]+)$')] then return path end
end
local function digest(path)
  local file = io.open(path, 'rb')
  if not file then
    if uv.fs_stat(path) then error('ファイルを読み込めません: ' .. path) end
    return 'missing'
  end
  local data = file:read('*a')
  file:close()
  return vim.fn.sha256(data)
end
local function check_disk(buf, path)
  local changed = false
  local autocmd = vim.api.nvim_create_autocmd('FileChangedShell', {
    buffer=buf,
    callback=function()
      changed = true
      vim.v.fcs_choice = '' -- 外部変更の確認ダイアログを出さず中止する。
    end,
  })
  local ok, err = pcall(vim.cmd, 'checktime ' .. buf)
  vim.api.nvim_del_autocmd(autocmd)
  if not ok then error(err) end
  if changed then error('ディスク上のファイルが外部で変更されています: ' .. path) end
end
if not expected then
  local result = {}
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    if vim.api.nvim_buf_is_loaded(buf) and vim.bo[buf].buftype == '' and vim.bo[buf].modified then
      local path = path_for(buf)
      if path then
        check_disk(buf, path)
        if vim.bo[buf].readonly or not vim.bo[buf].modifiable then
          error('保存できないバッファ: ' .. path)
        end
        result[#result + 1] = { buf=buf, path=path,
          tick=vim.api.nvim_buf_get_changedtick(buf), disk=digest(path) }
      end
    end
  end
  return result
end
if not vim.api.nvim_buf_is_loaded(expected.buf)
    or path_for(expected.buf) ~= expected.path
    or vim.api.nvim_buf_get_changedtick(expected.buf) ~= expected.tick
    or digest(expected.path) ~= expected.disk then
  error('保存確認中に内容が変わりました。再実行してください: ' .. expected.path)
end
check_disk(expected.buf, expected.path)
vim.api.nvim_buf_call(expected.buf, function() vim.cmd('silent update') end)
if vim.bo[expected.buf].modified then error('変更が未保存です: ' .. expected.path) end
return true
]]

local function main()
  if vim.fn.has('nvim-0.12') == 0 then error('自動保存にはNeovim 0.12以上が必要です') end
  local servers = {}
  for index = 2, #arg do servers[#servers + 1] = arg[index] end
  if #servers == 0 then servers = vim.fn.serverlist({ peer=true }) end
  local seen, owners, pending = {}, {}, {}
  for _, server in ipairs(servers) do
    if server ~= vim.v.servername and not seen[server] then
      seen[server] = true
      local channel = vim.fn.sockconnect('pipe', server, { rpc=true })
      if channel == 0 then error('Neovimに接続できません: ' .. server) end
      channels[#channels + 1] = channel
      local buffers = vim.rpcrequest(channel, 'nvim_exec_lua', remote, {root})
      for _, buffer in ipairs(buffers) do
        if owners[buffer.path] then
          error('複数のNeovimで同じファイルが未保存です: ' .. buffer.path)
        end
        owners[buffer.path] = channel
        pending[#pending + 1] = buffer
      end
    end
  end
  -- 全ウィンドウの競合・読み取り専用を確認してから保存する。
  for _, buffer in ipairs(pending) do
    vim.rpcrequest(owners[buffer.path], 'nvim_exec_lua', remote, {root, buffer})
  end
  -- 保存フックや保存中の編集で未保存になったものがあればビルドを止める。
  for _, channel in ipairs(channels) do
    local remaining = vim.rpcrequest(channel, 'nvim_exec_lua', remote, {root})
    if #remaining > 0 then error('未保存の編集が残っています。再実行してください') end
  end
  return { ok=true, saved=#pending, editors=#channels }
end

local ok, result = pcall(main)
for _, channel in ipairs(channels) do pcall(vim.fn.chanclose, channel) end
if not ok then result = {ok=false, error=tostring(result)} end
io.stdout:write(vim.json.encode(result), '\n')
