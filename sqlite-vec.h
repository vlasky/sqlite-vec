#ifndef SQLITE_VEC_H
#define SQLITE_VEC_H

#ifndef SQLITE_CORE
#include "sqlite3ext.h"
#else
#include "sqlite3.h"
#endif

#ifdef SQLITE_VEC_STATIC
  #if defined(__GNUC__) && !defined(_WIN32)
    #define SQLITE_VEC_API __attribute__((visibility("default")))
  #else
    #define SQLITE_VEC_API
  #endif
#else
  #ifdef _WIN32
    #define SQLITE_VEC_API __declspec(dllexport)
  #else
    #define SQLITE_VEC_API __attribute__((visibility("default")))
  #endif
#endif

#define SQLITE_VEC_VERSION "v0.2.9-alpha"
// TODO rm
#define SQLITE_VEC_DATE "2026-11-09T11:11:06Z+1100"
#define SQLITE_VEC_SOURCE "a66f28f97a9863c17e69e2611af80ddc7fedc2c4"


#define SQLITE_VEC_VERSION_MAJOR 0
#define SQLITE_VEC_VERSION_MINOR 2
#define SQLITE_VEC_VERSION_PATCH 9

#ifdef __cplusplus
extern "C" {
#endif

SQLITE_VEC_API int sqlite3_vec_init(sqlite3 *db, char **pzErrMsg,
                  const sqlite3_api_routines *pApi);

#ifdef __cplusplus
}  /* end of the 'extern "C"' block */
#endif

#endif /* ifndef SQLITE_VEC_H */
