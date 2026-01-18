/**
 * Application settings configurable from the startup modal.
 * Extensible: add new fields here and wire them up in StartupModal + App.
 */
export interface AppSettings {
    /** Use remote data_domain server vs mock data */
    useRemote: boolean;
    /** Data domain server URL (e.g. http://localhost:8000) */
    dataDomainUrl: string;
    /** S2 cell level for point+click shard selection (1-30) */
    s2CellLevel: number;
}

/** Default settings - remote server on localhost */
export const DEFAULT_SETTINGS: AppSettings = {
    useRemote: true,
    dataDomainUrl: 'http://localhost:8000',
    s2CellLevel: 12
};
