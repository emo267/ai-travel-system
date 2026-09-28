import request from './request'

export const createTask = (data) => request.post('/travel/tasks', data)
export const getTasks = () => request.get('/travel/tasks')
export const getTaskDetail = (id) => request.get(`/travel/tasks/${id}`)
export const generatePlan = (id) => request.post(`/travel/tasks/${id}/generate`)
export const getTaskStatus = (id) => request.get(`/travel/tasks/${id}/status`)
export const deleteTask = (id) => request.delete(`/travel/tasks/${id}`)