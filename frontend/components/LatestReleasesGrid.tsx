"use client";

import { useState } from "react";
import Link from "next/link";
import type { LatestRelease } from "@/lib/types";

interface LatestReleasesGridProps {
    initialReleases: LatestRelease[];
}

export default function LatestReleasesGrid({ initialReleases }: LatestReleasesGridProps) {
    const [currentPage, setCurrentPage] = useState(1);
    const itemsPerPage = 12;

    if (!initialReleases || initialReleases.length === 0) return null;

    // Pagination logic
    const totalPages = Math.ceil(initialReleases.length / itemsPerPage);
    const startIndex = (currentPage - 1) * itemsPerPage;
    const currentItems = initialReleases.slice(startIndex, startIndex + itemsPerPage);

    const handlePageChange = (newPage: number) => {
        setCurrentPage(newPage);
        // Scroll to top of section
        const section = document.querySelector(".latest-releases-section");
        if (section) {
            const offset = 100; // Offset for navbar
            const elementPosition = section.getBoundingClientRect().top;
            const offsetPosition = elementPosition + window.pageYOffset - offset;
            
            window.scrollTo({
                top: offsetPosition,
                behavior: "smooth"
            });
        }
    };

    return (
        <section className="latest-releases-section container-wide">
            <div className="section-header-flex" style={{ 
                display: 'flex', 
                justifyContent: 'space-between', 
                alignItems: 'center', 
                marginBottom: '2rem',
                borderBottom: '1px solid var(--border-subtle)',
                paddingBottom: '0.75rem'
            }}>
                <h2 className="section-heading" style={{ margin: 0 }}>Latest Releases</h2>
                {totalPages > 1 && (
                    <div className="pagination-info" style={{ 
                        fontSize: '0.9rem', 
                        fontWeight: '500',
                        color: 'var(--text-secondary)',
                        background: 'var(--bg-surface)',
                        padding: '0.3rem 0.8rem',
                        borderRadius: 'var(--radius-sm)',
                        border: '1px solid var(--border-subtle)'
                    }}>
                        Page {currentPage} of {totalPages}
                    </div>
                )}
            </div>

            <div className="latest-grid">
                {currentItems.map((rel: LatestRelease, idx: number) => (
                    <div key={`${rel.session}-${idx}`} className="latest-card-wrapper">
                        {rel.mal_id ? (
                            <Link href={`/watch/${rel.mal_id}/${rel.episode}?from=latest`} className="latest-card">
                                <div className="latest-image-wrapper">
                                    <img src={rel.snapshot} alt={rel.title} loading="lazy" />
                                    <div className="latest-card-overlay">
                                        <div className="latest-header-row">
                                            <p className="latest-title">{rel.title}</p>
                                            <span className="latest-episode-number">{rel.display_episode || rel.episode}</span>
                                        </div>
                                    </div>
                                </div>
                            </Link>
                        ) : (
                            <div className="latest-card disabled">
                                <div className="latest-image-wrapper">
                                    <img src={rel.snapshot} alt={rel.title} loading="lazy" />
                                    <div className="latest-card-overlay">
                                        <div className="latest-header-row">
                                            <p className="latest-title">{rel.title}</p>
                                            <span className="latest-episode-number">{rel.display_episode || rel.episode}</span>
                                        </div>
                                        <span className="latest-status-badge">Mapping...</span>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {totalPages > 1 && (
                <div className="pagination-container" style={{
                    marginTop: '4rem',
                    padding: '2rem 0',
                    borderTop: '1px solid var(--border-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '1rem'
                }}>
                    <div className="pagination-bar" style={{ 
                        display: 'flex', 
                        justifyContent: 'center', 
                        alignItems: 'center', 
                        gap: '0.75rem', 
                    }}>
                        <button 
                            onClick={() => handlePageChange(currentPage - 1)}
                            disabled={currentPage === 1}
                            className={`page-btn ${currentPage === 1 ? 'disabled' : ''}`}
                            style={{
                                padding: '0.6rem 1.25rem',
                                background: 'var(--bg-surface)',
                                border: '1px solid var(--border-subtle)',
                                borderRadius: 'var(--radius-md)',
                                color: currentPage === 1 ? 'var(--text-muted)' : 'var(--text-primary)',
                                opacity: currentPage === 1 ? 0.5 : 1,
                                cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                                fontSize: '0.9rem',
                                fontWeight: '600',
                                transition: 'all 0.2s ease'
                            }}
                        >
                            Previous
                        </button>
                        
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                            {[...Array(totalPages)].map((_, i) => {
                                const pageNum = i + 1;
                                
                                if (
                                    totalPages > 5 && 
                                    pageNum !== 1 && 
                                    pageNum !== totalPages && 
                                    (pageNum < currentPage - 1 || pageNum > currentPage + 1)
                                ) {
                                    if (pageNum === currentPage - 2 || pageNum === currentPage + 2) {
                                        return <span key={pageNum} style={{ color: 'var(--text-muted)', alignSelf: 'center', padding: '0 0.25rem' }}>...</span>;
                                    }
                                    return null;
                                }

                                return (
                                    <button
                                        key={pageNum}
                                        onClick={() => handlePageChange(pageNum)}
                                        className={`page-num-btn ${currentPage === pageNum ? 'active' : ''}`}
                                        style={{
                                            width: '40px',
                                            height: '40px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            borderRadius: 'var(--radius-md)',
                                            background: currentPage === pageNum ? 'var(--gold)' : 'var(--bg-surface)',
                                            color: currentPage === pageNum ? '#000' : 'var(--text-primary)',
                                            border: '1px solid',
                                            borderColor: currentPage === pageNum ? 'var(--gold)' : 'var(--border-subtle)',
                                            fontWeight: '700',
                                            fontSize: '0.9rem',
                                            transition: 'all 0.2s ease',
                                            boxShadow: currentPage === pageNum ? '0 0 15px var(--gold-glow)' : 'none'
                                        }}
                                    >
                                        {pageNum}
                                    </button>
                                );
                            })}
                        </div>

                        <button 
                            onClick={() => handlePageChange(currentPage + 1)}
                            disabled={currentPage === totalPages}
                            className={`page-btn ${currentPage === totalPages ? 'disabled' : ''}`}
                            style={{
                                padding: '0.6rem 1.25rem',
                                background: 'var(--bg-surface)',
                                border: '1px solid var(--border-subtle)',
                                borderRadius: 'var(--radius-md)',
                                color: currentPage === totalPages ? 'var(--text-muted)' : 'var(--text-primary)',
                                opacity: currentPage === totalPages ? 0.5 : 1,
                                cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                                fontSize: '0.9rem',
                                fontWeight: '600',
                                transition: 'all 0.2s ease'
                            }}
                        >
                            Next
                        </button>
                    </div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        Showing {startIndex + 1}-{Math.min(startIndex + itemsPerPage, initialReleases.length)} of {initialReleases.length} releases
                    </div>
                </div>
            )}
        </section>
    );
}
