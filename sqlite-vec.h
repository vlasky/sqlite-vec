#ifndef SQLITE_VEC_H
#define SQLITE_VEC_H

#ifndef SQLITE_CORE
#include "sqlite3ext.h"
#else
#include "sqlite3.h"
#endif

#ifdef SQLITE_VEC_STATIC
  #define SQLITE_VEC_API __attribute__((visibility("default")))
#else
  #ifdef _WIN32
    #define SQLITE_VEC_API __declspec(dllexport)
  #else
    #define SQLITE_VEC_API __attribute__((visibility("default")))
  #endif
#endif

#define SQLITE_VEC_VERSION "v0.2.6-alpha"
// TODO rm
#define SQLITE_VEC_DATE "2026-08-22T16:19:42Z+1000"
#define SQLITE_VEC_SOURCE "ab69590a379a9373d71e061677036a6debe0c5a7"


#define SQLITE_VEC_VERSION_MAJOR 0
#define SQLITE_VEC_VERSION_MINOR 2
#define SQLITE_VEC_VERSION_PATCH 6

#ifdef __cplusplus
extern "C" {
#endif

SQLITE_VEC_API int sqlite3_vec_init(sqlite3 *db, char **pzErrMsg,
                  const sqlite3_api_routines *pApi);

#ifdef __cplusplus
}  /* end of the 'extern "C"' block */
#endif

#endif /* ifndef SQLITE_VEC_H */
