import { describe, expect, it } from 'vitest'
import { localCameraBase } from '../src/command/live/camera'

describe('rover camera URL', () => {
  it('accepts only a plain HTTP loopback origin', () => {
    expect(localCameraBase('http://127.0.0.1:18080')).toBe('http://127.0.0.1:18080')
    expect(localCameraBase('http://localhost:18080/')).toBe('http://localhost:18080')
    for (const value of ['http://10.192.59.13:18080', 'https://localhost:18080', 'http://user:secret@localhost:18080', 'http://localhost:18080/health', 'http://localhost:18080/?token=x', 'not a url']) {
      expect(localCameraBase(value)).toBeNull()
    }
  })
})
