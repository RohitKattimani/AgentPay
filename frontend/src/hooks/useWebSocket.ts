import { useEffect, useCallback, useRef } from 'react'

export function useWebSocket(taskId: number, onMessage: (data: any) => void) {
  const wsRef = useRef<WebSocket | null>(null)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/tasks/${taskId}`
    
    wsRef.current = new WebSocket(wsUrl)

    wsRef.current.onopen = () => {
      console.log(`WebSocket connected for task ${taskId}`)
    }

    wsRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onMessageRef.current(data)
      } catch (e) {
        console.error('Failed to parse WebSocket message', e)
      }
    }

    wsRef.current.onclose = () => {
      console.log(`WebSocket disconnected for task ${taskId}`)
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [taskId])

  const send = useCallback((data: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  return { send }
}
