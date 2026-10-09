/** 上游 asset-url.ts 还要给三维模型算带哈希的路径，这里没有模型，只留基路径。 */
export const assetUrl = (path: string) => `${import.meta.env.BASE_URL}${path}`;
