/**
 * muxiaolei desktop half — native SDK member search + balance summary (read-only UI).
 * Folder id must be muxiaolei. Loaded from ~/.hermes/desktop-plugins/muxiaolei/plugin.js
 * and mirrored under ~/.hermes/plugins/muxiaolei/desktop/plugin.js (unified package).
 */
import {
  Button,
  EmptyState,
  ErrorState,
  GlyphSpinner,
  Input,
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  host,
  useQuery,
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useState } from 'react'

const ID = 'muxiaolei'
const PAGE_PATH = '/muxiaolei-members'
const NAV_LABEL = '木小垒会员'

function MemberPane({ rest }) {
  const [keyword, setKeyword] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [selectedId, setSelectedId] = useState(null)

  const health = useQuery({
    queryKey: [ID, 'health'],
    queryFn: () => rest('/health'),
    refetchInterval: 15000,
  })
  const list = useQuery({
    queryKey: [ID, 'members', submitted],
    queryFn: () => rest(`/members?keyword=${encodeURIComponent(submitted)}&page=1&size=8`),
  })
  const bal = useQuery({
    queryKey: [ID, 'bal', selectedId],
    enabled: !!selectedId,
    queryFn: () => rest(`/members/${encodeURIComponent(selectedId)}/balance`),
  })

  const offline = health.isError || (health.data && health.data.reachable === false)
  const items = (list.data && list.data.items) || []

  return jsxs('div', {
    className: 'flex h-full flex-col gap-3 p-3 text-sm',
    children: [
      jsxs('div', {
        className: 'flex items-center justify-between gap-2',
        children: [
          jsx('div', { className: 'font-medium', children: NAV_LABEL }),
          health.isLoading
            ? jsx(GlyphSpinner, {})
            : jsx('span', {
                className: 'text-[0.6875rem] text-(--ui-text-tertiary)',
                children: offline
                  ? '业务离线'
                  : `在线 ${((health.data && health.data.version) || '').toString()}`,
              }),
        ],
      }),
      offline
        ? jsx(ErrorState, {
            title: '木小垒业务后端离线',
            description: (health.data && health.data.message) || '请先启动本机服务 127.0.0.1:18080',
          })
        : null,
      jsxs('div', {
        className: 'flex gap-2',
        children: [
          jsx(Input, {
            value: keyword,
            placeholder: '搜索会员关键词',
            onChange: (e) => setKeyword(e.target.value),
            onKeyDown: (e) => {
              if (e.key === 'Enter') setSubmitted(keyword.trim())
            },
          }),
          jsx(Button, {
            size: 'sm',
            onClick: () => setSubmitted(keyword.trim()),
            children: '搜索',
          }),
        ],
      }),
      jsx('div', {
        className: 'text-[0.6875rem] text-(--ui-text-tertiary)',
        children: '可自然语言：查会员→余额；预约/开单/充值先 prepare，再在 127.0.0.1:18085 确认。本页只读。',
      }),
      list.isLoading
        ? jsx(GlyphSpinner, {})
        : list.isError
          ? jsx(ErrorState, {
              title: '查询失败',
              description: String((list.error && list.error.message) || list.error || ''),
            })
          : items.length === 0
            ? jsx(EmptyState, { title: '无结果', description: '换个关键词，或确认业务服务已登录账号有权限' })
            : jsx('div', {
                className: 'flex flex-col gap-1 overflow-auto',
                children: items.map((it) =>
                  jsxs(
                    'button',
                    {
                      type: 'button',
                      className:
                        'flex flex-col items-start gap-0.5 rounded-md border border-(--ui-stroke-secondary) px-2 py-1.5 text-left hover:bg-(--chrome-action-hover)',
                      onClick: () => setSelectedId(String(it.customer_id)),
                      children: [
                        jsx('div', {
                          className: 'font-medium',
                          children: it.ref || `id:${it.customer_id}`,
                        }),
                        jsx('div', {
                          className: 'text-[0.6875rem] text-(--ui-text-tertiary)',
                          children: `${it.membership_type || '-'} · ${it.phone_masked || '***'} · ${it.status || ''}`,
                        }),
                      ],
                    },
                    String(it.customer_id),
                  ),
                ),
              }),
      selectedId
        ? jsxs('div', {
            className: 'rounded-md border border-(--ui-stroke-secondary) p-2',
            children: [
              jsx('div', { className: 'text-[0.6875rem] text-(--ui-text-tertiary)', children: '余额摘要' }),
              bal.isLoading
                ? jsx(GlyphSpinner, {})
                : bal.isError
                  ? jsx('div', { children: '余额读取失败' })
                  : jsx('div', {
                      className: 'font-medium',
                      children: bal.data && bal.data.success === false
                        ? bal.data.error || '失败'
                        : `储值可用（已加载，界面内显示；不写入聊天）`,
                    }),
              bal.data && bal.data.balance != null
                ? jsx('div', {
                    className: 'mt-1 text-lg tabular-nums',
                    children: String(bal.data.balance),
                  })
                : null,
            ],
          })
        : null,
      jsx(Button, {
        size: 'sm',
        onClick: () => host.notify({ kind: 'info', message: '扣款/改偏好：让对话调用 prepare 工具后，请到 127.0.0.1:18085 确认' }),
        children: '打开确认说明',
      }),
    ],
  })
}

export default {
  id: ID,
  name: '木小垒会员',
  defaultEnabled: true,
  register(ctx) {
    const rest = (path, opts) => ctx.rest(path, opts)

    ctx.register({
      id: 'page',
      area: ROUTES_AREA,
      title: NAV_LABEL,
      data: { path: PAGE_PATH },
      render: () => jsx(MemberPane, { rest }),
    })

    ctx.register({
      id: 'nav',
      area: SIDEBAR_NAV_AREA,
      order: 80,
      data: {
        path: PAGE_PATH,
        label: NAV_LABEL,
        codicon: 'organization',
      },
    })

    ctx.register({
      id: 'palette',
      area: PALETTE_AREA,
      data: {
        id: 'open',
        title: '打开 木小垒会员',
        subtitle: '只读会员搜索与余额',
        keywords: ['muxiaolei', '会员', '余额'],
        onSelect: () => host.navigate(PAGE_PATH),
      },
    })
  },
}
